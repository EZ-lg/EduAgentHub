"""
全局总览聚合 API（2.0 P5 G4/G5）

- GET /api/overview                 全局总览：统计条 + 学生卡片流 + 待办区
- GET /api/students/{id}/overview   学生总览聚合（学科卡片 / 班级 / 课表 / 报告状态）

设计口径：
- 「待排课」= 已启用但没有已确认课次的学期班（智能排课的候选 draft 不落库，
  故库中无 draft 行；以此口径让待办可直达"班级详情→智能排课"）
- 「本周课次」= 学期班 active 课次行数 + 班期内寒暑假班本周实际上课天数（周一~周六，周日休息）
- 今日有课 = 混合解析：学期班按周几 + 寒暑假班按班期日期（复用 P4 课表口径）
"""
import json
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.models import get_db
from backend.models.activity_log import ActivityLog
from backend.models.class_ import Class
from backend.models.class_student import ClassStudent
from backend.models.class_schedule import ClassSchedule
from backend.models.classroom import Classroom
from backend.models.course_plan import CoursePlan
from backend.models.report import Report
from backend.models.score import Score
from backend.models.student import Student
from backend.models.subject import Subject
from backend.models.teacher import Teacher
from backend.services.term_schedule import compute_end_date
from backend.utils.helpers import success_response

router = APIRouter(prefix="/api", tags=["overview"])

WEEK_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


# ---------------------------------------------------------------- 日期工具
def _monday_of(today: date) -> date:
    return today - timedelta(days=today.weekday())


def _summer_lessons_in_week(start: str, end: str, today: date) -> int:
    """寒暑假班本周实际上课天数：周一~周六上课、周日休息，仅统计落在班期内的日期。"""
    try:
        s = datetime.strptime(start, "%Y-%m-%d").date()
        e = datetime.strptime(end, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return 0
    monday = _monday_of(today)
    sunday = monday + timedelta(days=6)
    count = 0
    d = max(s, monday)
    while d <= min(e, sunday):
        if d.weekday() != 6:
            count += 1
        d += timedelta(days=1)
    return count


# ---------------------------------------------------------------- 全局总览
def _global_context(db: Session) -> dict:
    """一次算好全局总览所需的公共数据：各班课次数、本周寒暑假课次数、学生班级映射等"""
    today = date.today()
    # 学期班 active 课次 → 每班每周课次数
    sched_counts = {}
    for r in db.query(ClassSchedule).filter(ClassSchedule.status == "active").all():
        sched_counts[r.class_id] = sched_counts.get(r.class_id, 0) + 1
    # 寒暑假班 → 本周实际上课天数
    summer_lessons = {}
    for c in db.query(Class).filter(
            Class.status == "active", Class.term_type == "summer_winter").all():
        end = c.end_date or compute_end_date(c.start_date, c.total_lessons or 0)
        summer_lessons[c.id] = _summer_lessons_in_week(c.start_date, end, today)
    # 学生在读班级映射（仅 active 班级）
    student_classes = {}
    for sid, cid in db.query(ClassStudent.student_id, ClassStudent.class_id).join(
            Class, ClassStudent.class_id == Class.id
    ).filter(Class.status == "active").all():
        student_classes.setdefault(sid, []).append(cid)
    return {
        "sched_counts": sched_counts,
        "summer_lessons": summer_lessons,
        "student_classes": student_classes,
        "today": today,
    }


def _student_weekly_sessions(ctx: dict, sid: int) -> int:
    """某生本周课次：学期班 active 课次 + 班期内寒暑假班本周天数"""
    counts, summer, classes = ctx["sched_counts"], ctx["summer_lessons"], ctx["student_classes"]
    total = 0
    for cid in classes.get(sid, []):
        total += counts.get(cid, 0) + summer.get(cid, 0)
    return total


def _latest_report_map(db: Session) -> dict:
    """{student_id: {status, subject_name, created_at}} 最近报告（按 created_at 倒序取首条）"""
    result = {}
    rows = db.query(Report, Subject).join(Subject, Report.subject_id == Subject.id).order_by(
        Report.created_at.desc()).all()
    for r, sub in rows:
        result.setdefault(sub.student_id, {
            "status": r.status, "subject_name": sub.name, "created_at": r.created_at,
        })
    return result


@router.get("/overview")
def global_overview(db: Session = Depends(get_db)):
    """全局总览：统计条 + 学生卡片流 + 待办区"""
    today = date.today()
    wd = today.weekday()
    ctx = _global_context(db)

    # ---- 统计条 ----
    active_students = db.query(Student).filter(Student.status == "active").count()
    active_classes = db.query(Class).filter(Class.status == "active").count()
    teachers = db.query(Teacher).count()
    total_students = db.query(Student).count()
    weekly_sessions = sum(ctx["sched_counts"].values()) + sum(ctx["summer_lessons"].values())

    # 待排课 = 已启用学期班无任何已确认课次
    scheduled_class_ids = set(ctx["sched_counts"].keys())
    pending_classes = db.query(Class).filter(
        Class.status == "active", Class.term_type == "semester").all()
    pending_ids = [c.id for c in pending_classes if c.id not in scheduled_class_ids]

    # ---- 学生卡片流 ----
    report_map = _latest_report_map(db)
    active_subjects = {}
    for sid, name in db.query(Subject.student_id, Subject.name).filter(
            Subject.status == "active").all():
        active_subjects.setdefault(sid, []).append(name)
    class_counts = {}
    for sid, ids in ctx["student_classes"].items():
        class_counts[sid] = len(ids)

    students = db.query(Student).order_by(
        Student.status.asc(), Student.updated_at.desc()).limit(200).all()
    student_cards = []
    for s in students:
        rep = report_map.get(s.id)
        student_cards.append({
            "id": s.id,
            "name": s.name,
            "grade": s.grade,
            "status": s.status,
            "subjects": active_subjects.get(s.id, []),
            "subject_count": len(active_subjects.get(s.id, [])),
            "class_count": class_counts.get(s.id, 0),
            "weekly_sessions": _student_weekly_sessions(ctx, s.id),
            "report_status": rep["status"] if rep else None,
            "report_subject": rep["subject_name"] if rep else None,
        })

    # ---- 待办区 ----
    # a) 待排课班级
    pending_list = []
    for c in pending_classes:
        if c.id in scheduled_class_ids:
            continue
        pending_list.append(_class_summary(db, c))
    # b) 今日有课班级（混合解析：学期班按周几 + 寒暑假班按班期日期）
    today_classes = _today_classes(db, today, wd)
    # c) 最近活动（复用工作台口径，取 10 条）
    activities = _recent_activities(db, 10)

    return success_response({
        "stats": {
            "active_students": active_students,
            "active_classes": active_classes,
            "weekly_sessions": weekly_sessions,
            "teachers": teachers,
            "pending_schedule": len(pending_list),
            "total_students": total_students,
            "today_classes": len(today_classes),
        },
        "students": student_cards,
        "todos": {
            "pending_schedule": pending_list,
            "today_classes": today_classes,
            "activities": activities,
        },
    })


def _class_summary(db: Session, cls: Class) -> dict:
    """班级概要（待办/卡片共用）：关联名称 + 人数 + 排课摘要"""
    teacher = db.query(Teacher).filter(Teacher.id == cls.teacher_id).first() if cls.teacher_id else None
    room = db.query(Classroom).filter(Classroom.id == cls.classroom_id).first() if cls.classroom_id else None
    student_count = db.query(ClassStudent).filter(ClassStudent.class_id == cls.id).count()
    return {
        "id": cls.id,
        "name": cls.name,
        "class_type": cls.class_type,
        "term_type": cls.term_type,
        "status": cls.status,
        "subject_name": cls.subject_name or "",
        "teacher_name": teacher.name if teacher else "",
        "classroom_name": room.name if room else "",
        "student_count": student_count,
        "weekly_frequency": cls.weekly_frequency,
        "daily_start": cls.daily_start,
        "daily_end": cls.daily_end,
        "total_lessons": cls.total_lessons,
        "start_date": cls.start_date,
        "end_date": cls.end_date,
    }


def _today_classes(db: Session, today: date, wd: int) -> list:
    """今天有课的班级（混合解析，与课表 /api/schedules/day 口径一致）"""
    result = []
    today_str = today.isoformat()
    # 周循环课（date 为空）：active 课次 weekday 匹配
    rows = db.query(ClassSchedule, Class).join(Class, ClassSchedule.class_id == Class.id).filter(
        ClassSchedule.status == "active", ClassSchedule.weekday == wd,
        ClassSchedule.date == "").all()
    seen = set()
    for sched, cls in rows:
        seen.add(cls.id)
        item = _class_summary(db, cls)
        item["start_time"] = sched.start_time
        item["end_time"] = sched.end_time
        item["weekday"] = wd
        item["is_adhoc"] = False
        result.append(item)
    # 临时调课：date 精确匹配今天
    adhoc_rows = db.query(ClassSchedule, Class).join(Class, ClassSchedule.class_id == Class.id).filter(
        ClassSchedule.status == "active", ClassSchedule.date == today_str).all()
    for sched, cls in adhoc_rows:
        seen.add(cls.id)
        item = _class_summary(db, cls)
        item["start_time"] = sched.start_time
        item["end_time"] = sched.end_time
        item["weekday"] = wd
        item["is_adhoc"] = True
        result.append(item)
    # 寒暑假班：班期内且非周日
    if wd != 6:
        terms = db.query(Class).filter(
            Class.status == "active", Class.term_type == "summer_winter").all()
        today_str = today.isoformat()
        for t in terms:
            if t.id in seen:
                continue
            if not t.start_date or not t.daily_start or not t.daily_end:
                continue
            end = t.end_date or compute_end_date(t.start_date, t.total_lessons or 0)
            if not (t.start_date <= today_str <= end):
                continue
            item = _class_summary(db, t)
            item["start_time"] = t.daily_start
            item["end_time"] = t.daily_end
            item["weekday"] = wd
            result.append(item)
    result.sort(key=lambda x: x.get("start_time", ""))
    return result


def _recent_activities(db: Session, limit: int = 10) -> list:
    """最近活动（join 学生/学科名渲染）"""
    rows = db.query(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(limit).all()
    result = []
    for a in rows:
        d = a.to_dict()
        if a.subject_id:
            subj = db.get(Subject, a.subject_id)
            if subj:
                d["subject_name"] = subj.name
                stu = db.get(Student, subj.student_id)
                if stu:
                    d["student_name"] = stu.name
        elif a.student_id:
            stu = db.get(Student, a.student_id)
            if stu:
                d["student_name"] = stu.name
        result.append(d)
    return result


# ---------------------------------------------------------------- 学生总览
def _linked_class(db: Session, student_id: int, subject: Subject):
    """找该生某学科对应的上课班级（优先一对1 的 subject_id 绑定，其次同名学科匹配）"""
    cs = db.query(ClassStudent).filter(
        ClassStudent.student_id == student_id,
        ClassStudent.subject_id == subject.id,
    ).first()
    if cs:
        cls = db.get(Class, cs.class_id)
        if cls:
            return cls
    if subject.name:
        cls = db.query(Class).join(ClassStudent, ClassStudent.class_id == Class.id).filter(
            ClassStudent.student_id == student_id,
            Class.status == "active",
            Class.subject_name == subject.name,
        ).first()
        if cls:
            return cls
    return None


@router.get("/students/{student_id}/overview")
def student_overview(student_id: int, db: Session = Depends(get_db)):
    """学生总览聚合：顶部统计 + 学科卡片 + 班级区"""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")

    ctx = _global_context(db)

    # ---- 统计 ----
    subjects = db.query(Subject).filter(Subject.student_id == student_id).all()
    active_subject_count = sum(1 for s in subjects if s.status == "active")
    class_count = len(ctx["student_classes"].get(student_id, []))
    weekly_sessions = _student_weekly_sessions(ctx, student_id)

    # ---- 学科卡片 ----
    subject_cards = []
    for sub in subjects:
        card = {
            "id": sub.id,
            "name": sub.name,
            "status": sub.status,
            "teacher_name": "",
            "class_name": "",
            "class_id": None,
            "class_type": "",
            "report": None,
            "plan": None,
            "scores": [],  # [[date, percent], ...] 最近 6 次升序，供迷你成绩线
        }
        cls = _linked_class(db, student_id, sub)
        if cls:
            teacher = db.get(Teacher, cls.teacher_id) if cls.teacher_id else None
            card["teacher_name"] = teacher.name if teacher else ""
            card["class_name"] = cls.name
            card["class_id"] = cls.id
            card["class_type"] = cls.class_type
        # 最近报告
        report = db.query(Report).filter(Report.subject_id == sub.id).order_by(
            Report.created_at.desc()).first()
        if report:
            card["report"] = {
                "id": report.id, "status": report.status,
                "title": report.title, "created_at": report.created_at,
            }
        # 课程规划进度（active 版本 + 课时统计）
        plan = db.query(CoursePlan).filter(
            CoursePlan.subject_id == sub.id, CoursePlan.status == "active").first()
        if plan:
            rows = []
            try:
                rows = json.loads(plan.plan_json or "[]")
                if not isinstance(rows, list):
                    rows = []
            except (json.JSONDecodeError, TypeError):
                rows = []
            hours = sum(int(r.get("hours") or 0) for r in rows if isinstance(r, dict))
            card["plan"] = {
                "version": plan.version,
                "lesson_count": len(rows),
                "total_hours": hours,
            }
        # 成绩迷你图（百分制，最近 6 次）
        scores = db.query(Score).filter(Score.subject_id == sub.id).order_by(
            Score.exam_date.desc()).limit(6).all()
        scores = sorted(scores, key=lambda x: x.exam_date)
        card["scores"] = [
            [s.exam_date, round(s.score / s.total_score * 100, 1)]
            for s in scores if s.total_score > 0
        ]
        subject_cards.append(card)

    # ---- 班级区（该生所有班级 + 排课摘要）----
    class_rows = db.query(Class, ClassStudent).join(
        ClassStudent, ClassStudent.class_id == Class.id
    ).filter(ClassStudent.student_id == student_id).order_by(Class.created_at.desc()).all()
    class_list = []
    for cls, _ in class_rows:
        item = _class_summary(db, cls)
        if cls.term_type == "semester":
            scheds = db.query(ClassSchedule).filter(
                ClassSchedule.class_id == cls.id, ClassSchedule.status == "active"
            ).order_by(ClassSchedule.weekday, ClassSchedule.start_time).all()
            item["schedules"] = [{
                "weekday": s.weekday,
                "weekday_label": WEEK_NAMES[s.weekday] if 0 <= s.weekday < 7 else str(s.weekday),
                "start_time": s.start_time,
                "end_time": s.end_time,
            } for s in scheds]
        else:
            item["schedules"] = []
        class_list.append(item)

    return success_response({
        "student": student.to_dict(),
        "stats": {
            "subject_count": len(subjects),
            "active_subject_count": active_subject_count,
            "class_count": class_count,
            "weekly_sessions": weekly_sessions,
        },
        "subjects": subject_cards,
        "classes": class_list,
    })
