"""
排课 & 课表 API（P3 智能排课核心）

- GET  /api/schedules/periods      节次模板（settings.class_periods，含默认）
- GET  /api/schedules/weekly       周课表（筛选 teacher/classroom/student/class）
- POST /api/schedules/auto-plan    智能排课 → Top-N 候选方案 + AI 点评
- POST /api/schedules/confirm      确认方案落库（draft→active，旧版归档）
- POST /api/schedules/check        冲突预检（手动排课前，不落库）
- POST /api/schedules              手动新增课次（带冲突校验）
- PUT  /api/schedules/{id}         改课次（带冲突校验）
- DELETE /api/schedules/{id}       删课次
"""
import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.ai.manager import ai_manager
from backend.ai.prompts.prompt_loader import render_prompt
from backend.models import get_db
from backend.models.class_ import Class
from backend.models.class_student import ClassStudent
from backend.models.class_schedule import ClassSchedule
from backend.models.classroom import Classroom
from backend.models.setting import Setting
from backend.models.student import Student
from backend.models.teacher import Teacher
from backend.utils.activity import log_activity
from backend.utils.helpers import success_response, now_iso
from backend.services import scheduler
from backend.services.term_schedule import compute_end_date

router = APIRouter(prefix="/api/schedules", tags=["schedules"])

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _to_min(t: str) -> int:
    """HH:MM → 分钟（时间区间校验用）"""
    try:
        h, m = str(t).split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return 0


def _validate_time_range(start: str, end: str):
    """校验时间格式与区间：end 必须晚于 start（防倒置区间绕过冲突检测）"""
    if not start or not end:
        raise HTTPException(status_code=400, detail="请填写开始与结束时间")
    if _to_min(end) <= _to_min(start):
        raise HTTPException(status_code=400, detail="结束时间需晚于开始时间")


def _to_weekday(value, default=0) -> int:
    """安全转 weekday 并钳制到 0-6（非法输入回退 default），避免 int() 抛 500"""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return v if 0 <= v <= 6 else default


def _enrich_conflicts(db, conflicts, weekday=None, start=None, end=None):
    """给冲突列表补全信息：冲突班级名 + 具体时间，让前端明确提示「哪一天哪节课和哪个班冲突」"""
    out = []
    for c in conflicts or []:
        c = dict(c)
        cid = c.get("with_class_id")
        name = ""
        if cid:
            row = db.query(Class).filter(Class.id == cid).first()
            name = row.name if row else ""
        c["with_class_name"] = name
        # 时间描述：优先 on_item（批量校验），其次新排课的时间
        item = c.get("on_item") or {}
        t_wd = item.get("weekday")
        t_start = item.get("start_time")
        t_end = item.get("end_time")
        if t_wd is None and weekday is not None:
            t_wd, t_start, t_end = weekday, start, end
        time_desc = ""
        if t_wd is not None:
            time_desc = f"{WEEKDAY_CN[t_wd] if 0 <= t_wd <= 6 else t_wd} {t_start or '?'}-{t_end or '?'}"
        c["time"] = time_desc
        if name:
            c["message"] = f"{time_desc}：{name} {c.get('message', '占用')}"
        out.append(c)
    return out

# 默认节次模板（机构白天上课，晚上不上；早上 9 点开始；10:30 前结束=上午一、10:30 后开始=上午二、16:00 前结束=下午三、16:00 后开始=下午四）
DEFAULT_PERIODS = [
    {"label": "上午一", "start": "09:00", "end": "10:30"},
    {"label": "上午二", "start": "10:30", "end": "12:00"},
    {"label": "下午三", "start": "14:00", "end": "16:00"},
    {"label": "下午四", "start": "16:00", "end": "18:00"},
]
PERIODS_KEY = "class_periods"


def _read_periods(db: Session) -> List[dict]:
    """读取节次模板（settings.class_periods），无则返回默认"""
    row = db.query(Setting).filter(Setting.key == PERIODS_KEY).first()
    if not row or not row.value_json:
        return DEFAULT_PERIODS
    try:
        data = json.loads(row.value_json)
        if isinstance(data, list) and data:
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return DEFAULT_PERIODS


def _save_periods(db: Session, periods: List[dict]):
    row = db.query(Setting).filter(Setting.key == PERIODS_KEY).first()
    if not row:
        row = Setting(key=PERIODS_KEY)
        db.add(row)
    row.value_json = json.dumps(periods, ensure_ascii=False)


def _load_active_schedules(db: Session) -> List[dict]:
    """全部已确认课次（转 dict，供冲突占用）"""
    rows = db.query(ClassSchedule).filter(ClassSchedule.status == "active").all()
    items = []
    for r in rows:
        d = r.to_dict()
        d["student_ids"] = _class_student_ids(db, r.class_id)
        items.append(d)
    return items


def _class_student_ids(db: Session, class_id: int) -> List[int]:
    rows = db.query(ClassStudent).filter(ClassStudent.class_id == class_id).all()
    return [r.student_id for r in rows]


def _build_classes(db: Session, class_ids: List[int]) -> List[dict]:
    """组装排课输入：班级 + 教师 + 教室 + 学生 + 频率"""
    classes = []
    for cid in class_ids:
        cls = db.query(Class).filter(Class.id == cid).first()
        if not cls:
            continue
        if cls.status != "active":
            continue
        # 教室容量校验
        capacity = None
        if cls.classroom_id:
            room = db.query(Classroom).filter(Classroom.id == cls.classroom_id).first()
            capacity = room.capacity if room else None
        students = _class_student_ids(db, cls.id)
        if capacity is not None and len(students) > capacity:
            raise HTTPException(status_code=400,
                                detail=f"班级「{cls.name}」{len(students)} 人超过教室容量 {capacity} 人")
        classes.append({
            "id": cls.id,
            "name": cls.name,
            "class_type": cls.class_type,
            "teacher_id": cls.teacher_id,
            "classroom_id": cls.classroom_id,
            "student_ids": students,
            "weekly_frequency": cls.weekly_frequency or 1,
        })
    return classes


def _schedule_dict(db: Session, r: ClassSchedule, include_students: bool = True) -> dict:
    """课次 + 关联名称（班级/学科/教师/教室/学生）"""
    d = r.to_dict()
    cls = db.query(Class).filter(Class.id == r.class_id).first()
    d["class_name"] = cls.name if cls else ""
    d["subject_name"] = (cls.subject_name if cls else "") or ""
    teacher = db.query(Teacher).filter(Teacher.id == r.teacher_id).first() if r.teacher_id else None
    d["teacher_name"] = teacher.name if teacher else ""
    room = db.query(Classroom).filter(Classroom.id == r.classroom_id).first() if r.classroom_id else None
    d["classroom_name"] = room.name if room else ""
    if include_students:
        rows = db.query(ClassStudent, Student).join(Student, ClassStudent.student_id == Student.id) \
            .filter(ClassStudent.class_id == r.class_id).all()
        d["students"] = [{"id": s.id, "name": s.name} for _, s in rows]
    return d


def _ai_evaluate(db: Session, plan: dict, classes: List[dict]) -> Optional[str]:
    """对单个方案生成 AI 点评（未配 LLM 或失败时返回 None，优雅降级）"""
    llm = ai_manager.get_llm()
    if not llm:
        return None
    try:
        # 方案摘要
        plan_summary = []
        for cls in classes:
            items = plan.get(cls["id"], [])
            if items:
                plan_summary.append({
                    "班级": cls["name"],
                    "课次": [f"周{it['weekday'] + 1} {it['start_time']}-{it['end_time']}" for it in items],
                })
        # 教师负荷
        teacher_load = {}
        for cls in classes:
            tid = cls.get("teacher_id")
            name = f"教师#{tid}" if tid else "未指派"
            cnt = len(plan.get(cls["id"], []))
            teacher_load.setdefault(name, 0)
            teacher_load[name] += cnt
        # 学生负担（跨班合计）
        student_load = {}
        for cls in classes:
            for sid in cls.get("student_ids", []):
                student_load.setdefault(sid, 0)
                student_load[sid] += len(plan.get(cls["id"], []))
        system = render_prompt("system_prompt.txt")
        user = render_prompt("schedule_eval.txt",
                             plan_json=json.dumps(plan_summary, ensure_ascii=False),
                             teacher_load=json.dumps(teacher_load, ensure_ascii=False),
                             student_load=json.dumps(student_load, ensure_ascii=False))
        resp = llm.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        text = resp if isinstance(resp, str) else (resp.get("content") if isinstance(resp, dict) else str(resp))
        return text[:500]
    except Exception:
        return None


@router.get("/periods")
def get_periods(db: Session = Depends(get_db)):
    """节次模板"""
    return success_response(_read_periods(db))


@router.put("/periods")
def update_periods(data: dict, db: Session = Depends(get_db)):
    """更新节次模板（数组，每项 {label,start,end}）"""
    periods = data.get("periods")
    if not isinstance(periods, list) or not periods:
        raise HTTPException(status_code=400, detail="periods 需为非空数组")
    for p in periods:
        if not p.get("start") or not p.get("end"):
            raise HTTPException(status_code=400, detail="每个时段需含 start/end")
    _save_periods(db, periods)
    db.commit()
    return success_response(periods)


@router.get("/weekly")
def weekly_schedule(teacher_id: int = None, classroom_id: int = None,
                    student_id: int = None, class_id: int = None,
                    db: Session = Depends(get_db)):
    """周课表（默认全部 active 课次，可按教师/教室/学生/班级筛选）"""
    query = db.query(ClassSchedule).filter(ClassSchedule.status == "active")
    if teacher_id:
        query = query.filter(ClassSchedule.teacher_id == teacher_id)
    if classroom_id:
        query = query.filter(ClassSchedule.classroom_id == classroom_id)
    if class_id:
        query = query.filter(ClassSchedule.class_id == class_id)
    if student_id:
        # 该学生所在班级的课次
        class_ids = [r.class_id for r in
                     db.query(ClassStudent).filter(ClassStudent.student_id == student_id).all()]
        if not class_ids:
            return success_response({"items": [], "weekly": {d: [] for d in range(7)}})
        query = query.filter(ClassSchedule.class_id.in_(class_ids))
    rows = query.all()
    items = [_schedule_dict(db, r) for r in rows]
    weekly = scheduler.schedule_to_weekly(items)
    return success_response({"items": items, "weekly": weekly})


@router.get("/day")
def day_schedule(date: str, db: Session = Depends(get_db)):
    """按日期解析当天课次（混合模式）：
    - 学期班：该日期是周几 → 对应的 active 周循环课
    - 寒暑假班：日期在班期内且非周日 → 每天固定 1 节课
    """
    try:
        d = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式应为 YYYY-MM-DD")
    weekday = d.weekday()
    items = []

    # a) 周循环课（date 为空）：按 weekday 每周重复
    rows = db.query(ClassSchedule).filter(
        ClassSchedule.status == "active", ClassSchedule.weekday == weekday,
        ClassSchedule.date == "").all()
    for r in rows:
        item = _schedule_dict(db, r)
        item["is_adhoc"] = False
        items.append(item)

    # a2) 临时调课（date 精确匹配当天，一天可多节，计入总课时流程）
    adhoc = db.query(ClassSchedule).filter(
        ClassSchedule.status == "active", ClassSchedule.date == date).all()
    for r in adhoc:
        item = _schedule_dict(db, r)
        item["is_adhoc"] = True
        items.append(item)

    # b) 寒暑假班每天固定课（周日休息）
    if weekday != 6:
        terms = db.query(Class).filter(
            Class.term_type == "summer_winter", Class.status == "active").all()
        for t in terms:
            if not t.start_date or not t.daily_start or not t.daily_end:
                continue
            end = t.end_date or compute_end_date(t.start_date, t.total_lessons or 0)
            if not (t.start_date <= date <= end):
                continue
            teacher = db.query(Teacher).filter(Teacher.id == t.teacher_id).first() if t.teacher_id else None
            room = db.query(Classroom).filter(Classroom.id == t.classroom_id).first() if t.classroom_id else None
            rows_s = db.query(ClassStudent, Student).join(Student, ClassStudent.student_id == Student.id) \
                .filter(ClassStudent.class_id == t.id).all()
            items.append({
                "id": None, "class_id": t.id, "class_name": t.name,
                "subject_name": t.subject_name or "",
                "weekday": weekday, "start_time": t.daily_start, "end_time": t.daily_end,
                "classroom_id": t.classroom_id, "classroom_name": room.name if room else "",
                "teacher_id": t.teacher_id, "teacher_name": teacher.name if teacher else "",
                "students": [{"id": s.id, "name": s.name} for _, s in rows_s],
                "status": "active", "term_type": "summer_winter", "is_adhoc": False,
            })

    items.sort(key=lambda x: (x.get("start_time", ""), 0 if x.get("is_adhoc") else 1))
    return success_response({"date": date, "weekday": weekday, "items": items})


@router.post("/auto-plan")
def auto_plan(data: dict, db: Session = Depends(get_db)):
    """智能排课：class_ids 需要排课的班级；weekdays 可排的天（0-6，默认全部）"""
    class_ids = data.get("class_ids") or []
    if not class_ids:
        raise HTTPException(status_code=400, detail="请选择需要排课的班级")
    weekdays = data.get("weekdays")
    if weekdays is None:
        weekdays = list(range(7))
    else:
        # 只接受 0-6 的整数，非法值过滤，防止生成无效 weekday 落库后冲突检测被静默绕过
        weekdays = [d for d in weekdays if isinstance(d, int) and 0 <= d <= 6]
        if not weekdays:
            raise HTTPException(status_code=400, detail="weekdays 应为 0-6 的整数")

    classes = _build_classes(db, class_ids)
    if not classes:
        raise HTTPException(status_code=400, detail="所选班级不存在或未启用")

    periods = _read_periods(db)
    slots = [{"weekday": d, "start": p["start"], "end": p["end"], "label": p["label"]}
             for d in weekdays for p in periods]

    active = _load_active_schedules(db)
    solutions = scheduler.auto_plan(classes, active, slots, num_solutions=3)

    result = []
    for sol in solutions:
        # 方案课次挂班级信息（供前端预览）
        plan_view = {}
        for cls in classes:
            plan_view[cls["id"]] = [{
                "weekday": it["weekday"],
                "start_time": it["start_time"],
                "end_time": it["end_time"],
                "classroom_id": it.get("classroom_id"),
                "teacher_id": it.get("teacher_id"),
                "class_name": cls["name"],
            } for it in sol["plan"].get(cls["id"], [])]
        result.append({
            "score": sol["score"],
            "unmet": sol["unmet"],
            "plan": plan_view,
            "ai_comment": _ai_evaluate(db, sol["plan"], classes),
        })
    return success_response({
        "solutions": result,
        "periods": periods,
        "weekdays": weekdays,
    })


@router.post("/confirm")
def confirm_plan(data: dict, db: Session = Depends(get_db)):
    """确认排课方案：class_id + items 课次列表 → 落库 active，该班旧课次归档"""
    class_id = data.get("class_id")
    items = data.get("items") or []
    if not class_id or not items:
        raise HTTPException(status_code=400, detail="缺少 class_id 或 items")
    cls = db.query(Class).filter(Class.id == class_id).first()
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")

    # 组装候选并做全局冲突校验（含其他班 active 课次）
    new_items = []
    for it in items:
        new_items.append({
            "class_id": class_id,
            "weekday": _to_weekday(it["weekday"]),
            "start_time": it["start_time"],
            "end_time": it["end_time"],
            "classroom_id": it.get("classroom_id"),
            "teacher_id": it.get("teacher_id"),
            "student_ids": _class_student_ids(db, class_id),
        })
    # 冲突校验：排除本班旧课次（即将归档，避免「自己占自己」误判），
    # 只校验「新方案内部」+「新方案 vs 其他班 active 占用」
    existing = [r.to_dict() for r in db.query(ClassSchedule).filter(
        ClassSchedule.status == "active", ClassSchedule.class_id != class_id).all()]
    for r in existing:
        r["student_ids"] = _class_student_ids(db, r["class_id"])
    conflicts = scheduler.check_conflicts_batch(new_items)
    for it in new_items:
        for c in scheduler.check_conflict(existing, it):
            c["on_item"] = {
                "class_id": class_id,
                "weekday": it["weekday"],
                "start_time": it["start_time"],
                "end_time": it["end_time"],
            }
            conflicts.append(c)
    if conflicts:
        return success_response({"confirmed": False, "conflicts": _enrich_conflicts(db, conflicts),
                                 "message": "存在时间冲突，请调整后再确认"})

    # 该班旧"周循环"active 课次 → archived（临时调课 date 非空保留，教务手工排的课不抹掉）
    db.query(ClassSchedule).filter(
        ClassSchedule.class_id == class_id,
        ClassSchedule.status == "active",
        ClassSchedule.date == "",
    ).update({"status": "archived"})

    for it in new_items:
        db.add(ClassSchedule(
            class_id=class_id,
            weekday=it["weekday"],
            start_time=it["start_time"],
            end_time=it["end_time"],
            classroom_id=it["classroom_id"],
            teacher_id=it["teacher_id"],
            status="active",
        ))
    log_activity(db, "确认排课", f"班级「{cls.name}」{len(new_items)} 次课")
    db.commit()
    return success_response({"confirmed": True, "count": len(new_items)})


@router.post("/check")
def check_conflicts(data: dict, db: Session = Depends(get_db)):
    """冲突预检：items 候选课次（手动排课前用），返回全部冲突，不落库"""
    items = data.get("items") or []
    built = []
    for it in items:
        built.append({
            "class_id": it.get("class_id"),
            "weekday": _to_weekday(it.get("weekday", 0)),
            "start_time": it.get("start_time", ""),
            "end_time": it.get("end_time", ""),
            "classroom_id": it.get("classroom_id"),
            "teacher_id": it.get("teacher_id"),
            "student_ids": _class_student_ids(db, it.get("class_id")) if it.get("class_id") else [],
        })
    existing = [r.to_dict() for r in db.query(ClassSchedule).filter(ClassSchedule.status == "active").all()]
    for r in existing:
        r["student_ids"] = _class_student_ids(db, r["class_id"])
    conflicts = scheduler.check_conflicts_batch(existing + built)
    return success_response({"conflicts": _enrich_conflicts(db, conflicts)})


@router.post("/ad-hoc")
def add_ad_hoc_schedule(data: dict, db: Session = Depends(get_db)):
    """临时调课：为指定班级在指定日期加一节课（一天可多节，计入总课时流程）

    body: {class_id, date, start_time, end_time, classroom_id, teacher_id}
    仅在该日期生效一次（date 写入 class_schedules），冲突校验覆盖该时段所有已确认课次。
    """
    class_id = data.get("class_id")
    date = (data.get("date") or "").strip()
    start_time = (data.get("start_time") or "").strip()
    end_time = (data.get("end_time") or "").strip()
    if not class_id or not date:
        raise HTTPException(status_code=400, detail="请选择班级和日期")
    try:
        d = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式应为 YYYY-MM-DD")
    _validate_time_range(start_time, end_time)
    cls = db.query(Class).filter(Class.id == class_id).first()
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")
    weekday = d.weekday()

    new_item = {
        "class_id": class_id,
        "weekday": weekday,
        "start_time": start_time,
        "end_time": end_time,
        "classroom_id": data.get("classroom_id"),
        "teacher_id": data.get("teacher_id"),
        "student_ids": _class_student_ids(db, class_id),
    }
    # 冲突检测：所有 active 课次（周循环 + 其他临时课，含本班已有课次，防同班同时段双排）
    existing = [r.to_dict() for r in db.query(ClassSchedule).filter(ClassSchedule.status == "active").all()]
    for r in existing:
        r["student_ids"] = _class_student_ids(db, r["class_id"])
    conflicts = scheduler.check_conflict(existing, new_item)
    if conflicts:
        return success_response({"created": False,
                                 "conflicts": _enrich_conflicts(db, conflicts, weekday, start_time, end_time),
                                 "message": "该时段存在冲突，请调整后再试"})

    sched = ClassSchedule(
        class_id=class_id,
        weekday=weekday,
        start_time=start_time,
        end_time=end_time,
        date=date,
        classroom_id=data.get("classroom_id"),
        teacher_id=data.get("teacher_id"),
        status="active",
    )
    db.add(sched)
    log_activity(db, "临时调课", f"班级「{cls.name}」{date} {start_time}-{end_time}")
    db.commit()
    db.refresh(sched)
    return success_response({"created": True, "schedule": _schedule_dict(db, sched)})


@router.post("")
def add_schedule(data: dict, db: Session = Depends(get_db)):
    """手动新增课次（带冲突校验，冲突则 400 拒绝）"""
    class_id = data.get("class_id")
    if not class_id:
        raise HTTPException(status_code=400, detail="缺少 class_id")
    cls = db.query(Class).filter(Class.id == class_id).first()
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")
    _validate_time_range(data.get("start_time", ""), data.get("end_time", ""))
    try:
        weekday = int(data.get("weekday", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="weekday 应为 0-6 的整数")
    if not 0 <= weekday <= 6:
        raise HTTPException(status_code=400, detail="weekday 应为 0-6 的整数")
    new_item = {
        "class_id": class_id,
        "weekday": weekday,
        "start_time": data.get("start_time", ""),
        "end_time": data.get("end_time", ""),
        "classroom_id": data.get("classroom_id"),
        "teacher_id": data.get("teacher_id"),
        "student_ids": _class_student_ids(db, class_id),
    }
    existing = [r.to_dict() for r in db.query(ClassSchedule).filter(ClassSchedule.status == "active").all()]
    for r in existing:
        r["student_ids"] = _class_student_ids(db, r["class_id"])
    conflicts = scheduler.check_conflict(existing, new_item)
    if conflicts:
        return success_response({"created": False,
                                 "conflicts": _enrich_conflicts(db, conflicts, new_item["weekday"],
                                                                new_item["start_time"], new_item["end_time"]),
                                 "message": "存在时间冲突"})
    sched = ClassSchedule(
        class_id=class_id,
        weekday=new_item["weekday"],
        start_time=new_item["start_time"],
        end_time=new_item["end_time"],
        classroom_id=new_item["classroom_id"],
        teacher_id=new_item["teacher_id"],
        status="active",
    )
    db.add(sched)
    log_activity(db, "手动排课", f"班级「{cls.name}」添加课次")
    db.commit()
    db.refresh(sched)
    return success_response({"created": True, "schedule": _schedule_dict(db, sched)})


@router.put("/{schedule_id}")
def update_schedule(schedule_id: int, data: dict, db: Session = Depends(get_db)):
    """改课次（冲突校验排除自身）"""
    sched = db.query(ClassSchedule).filter(ClassSchedule.id == schedule_id).first()
    if not sched:
        raise HTTPException(status_code=404, detail="课次不存在")
    if "weekday" in data:
        try:
            wd = int(data["weekday"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="weekday 应为 0-6 的整数")
        if not 0 <= wd <= 6:
            raise HTTPException(status_code=400, detail="weekday 应为 0-6 的整数")
        sched.weekday = wd
    for f in ["start_time", "end_time", "classroom_id", "teacher_id"]:
        if f in data:
            setattr(sched, f, data[f])
    if "start_time" in data or "end_time" in data:
        _validate_time_range(sched.start_time, sched.end_time)
    db.flush()
    new_item = sched.to_dict()
    new_item["student_ids"] = _class_student_ids(db, sched.class_id)
    existing = [r.to_dict() for r in db.query(ClassSchedule)
                .filter(ClassSchedule.status == "active", ClassSchedule.id != schedule_id).all()]
    for r in existing:
        r["student_ids"] = _class_student_ids(db, r["class_id"])
    conflicts = scheduler.check_conflict(existing, new_item)
    if conflicts:
        db.rollback()
        return success_response({"updated": False,
                                 "conflicts": _enrich_conflicts(db, conflicts, new_item["weekday"],
                                                                new_item["start_time"], new_item["end_time"]),
                                 "message": "存在时间冲突"})
    db.commit()
    db.refresh(sched)
    return success_response({"updated": True, "schedule": _schedule_dict(db, sched)})


@router.delete("/{schedule_id}")
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    """删课次"""
    sched = db.query(ClassSchedule).filter(ClassSchedule.id == schedule_id).first()
    if not sched:
        raise HTTPException(status_code=404, detail="课次不存在")
    cls = db.query(Class).filter(Class.id == sched.class_id).first()
    log_activity(db, "删除课次", f"班级「{cls.name if cls else ''}」移除一次课")
    db.delete(sched)
    db.commit()
    return success_response({"deleted": True})
