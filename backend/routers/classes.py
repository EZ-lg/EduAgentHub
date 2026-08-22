"""
班级管理 API（2.0 上课维度核心）

覆盖：班级 CRUD + 学生增减 + 一对一快捷建班 + 增学生冲突预检（P3 排课完整校验）
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from backend.models import get_db
from backend.models.class_ import Class
from backend.models.class_schedule import ClassSchedule
from backend.models.class_student import ClassStudent
from backend.models.student import Student
from backend.models.subject import Subject
from backend.models.teacher import Teacher
from backend.models.classroom import Classroom
from backend.utils.activity import log_activity
from backend.utils.helpers import success_response, now_iso
from backend.services.term_schedule import compute_end_date, check_term_conflicts

router = APIRouter(prefix="/api/classes", tags=["classes"])


def _to_int(value, default=0):
    """整数字段归一化：前端表单可能传字符串（如 "5"），非法/空值回退 default"""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _class_detail(db: Session, cls: Class) -> dict:
    """班级详情：基础信息 + 人数 + 关联名称（教师/教室/学科）+ 学生列表"""
    d = cls.to_dict()
    teacher = db.query(Teacher).filter(Teacher.id == cls.teacher_id).first() if cls.teacher_id else None
    classroom = db.query(Classroom).filter(Classroom.id == cls.classroom_id).first() if cls.classroom_id else None
    subject = db.query(Subject).filter(Subject.id == cls.subject_id).first() if cls.subject_id else None
    d["teacher_name"] = teacher.name if teacher else ""
    d["classroom_name"] = classroom.name if classroom else ""
    # subject_name 优先用班级存的名字，兼容旧数据回退到关联学科
    d["subject_name"] = cls.subject_name or (subject.name if subject else "")

    # 学生列表（含姓名/年级/该班学科记录）
    rows = db.query(ClassStudent, Student).join(
        Student, ClassStudent.student_id == Student.id
    ).filter(ClassStudent.class_id == cls.id).all()
    students = []
    for cs, stu in rows:
        students.append({
            "class_student_id": cs.id,
            "student_id": stu.id,
            "name": stu.name,
            "grade": stu.grade,
            "subject_id": cs.subject_id,
            "enroll_date": cs.enroll_date,
            "status": cs.status,
        })
    d["student_count"] = len(students)
    d["students"] = students
    return d


@router.get("")
def list_classes(status: str = "", term_type: str = "", subject_id: int = None,
                 teacher_id: int = None, search: str = "", db: Session = Depends(get_db)):
    """班级列表（筛选：状态/上课模式/学科/教师/名称搜索），含人数与关联名称"""
    query = db.query(Class)
    if status in ("active", "paused"):
        query = query.filter(Class.status == status)
    if term_type in ("semester", "summer_winter"):
        query = query.filter(Class.term_type == term_type)
    if subject_id:
        query = query.filter(Class.subject_id == subject_id)
    if teacher_id:
        query = query.filter(Class.teacher_id == teacher_id)
    if search:
        query = query.filter(Class.name.contains(search))
    classes = query.order_by(Class.created_at.desc()).all()
    return success_response([_class_detail(db, c) for c in classes])


@router.post("")
def create_class(data: dict, db: Session = Depends(get_db)):
    """新建班级（可同时传 student_ids 批量添加学生）"""
    name = data.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="班级名称不能为空")
    class_type = data.get("class_type", "1vN")
    if class_type not in ("1v1", "1vN"):
        raise HTTPException(status_code=400, detail="班型应为 1v1 或 1vN")

    term_type = data.get("term_type", "semester")
    if term_type not in ("semester", "summer_winter"):
        raise HTTPException(status_code=400, detail="班型应为 semester（学期）或 summer_winter（寒暑假）")
    total_lessons = _to_int(data.get("total_lessons"))
    daily_start = data.get("daily_start", "")
    daily_end = data.get("daily_end", "")

    # 寒暑假班：班期自动计算（start + 总天数跳过周日）+ 必填校验
    end_date = data.get("end_date", "")
    if term_type == "summer_winter":
        if not data.get("start_date") or not daily_start or not daily_end or total_lessons <= 0:
            raise HTTPException(status_code=400, detail="寒暑假班需填写：开始日期、每天时段、总课次（天数）")
        end_date = compute_end_date(data["start_date"], total_lessons)

    cls = Class(
        name=name,
        subject_id=data.get("subject_id"),
        subject_name=data.get("subject_name", ""),
        teacher_id=data.get("teacher_id"),
        classroom_id=data.get("classroom_id"),
        class_type=class_type,
        term_type=term_type,
        total_lessons=total_lessons,
        daily_start=daily_start,
        daily_end=daily_end,
        weekly_frequency=_to_int(data.get("weekly_frequency"), 2),
        duration_minutes=_to_int(data.get("duration_minutes"), 120),
        start_date=data.get("start_date", ""),
        end_date=end_date,
        notes=data.get("notes", ""),
    )
    db.add(cls)
    db.flush()

    # 批量添加学生（一对一强制只允许 1 人）
    student_ids = data.get("student_ids") or []
    if class_type == "1v1" and len(student_ids) > 1:
        db.delete(cls)
        raise HTTPException(status_code=400, detail="一对一班级只能添加 1 名学生")
    for sid in student_ids:
        if not db.query(Student).filter(Student.id == sid).first():
            continue  # 忽略不存在的学生
        db.add(ClassStudent(class_id=cls.id, student_id=sid,
                            subject_id=data.get("subject_id") if class_type == "1v1" else None))
        log_activity(db, "加入班级", f"学生加入班级「{cls.name}」", student_id=sid)

    # 寒暑假班班期冲突校验
    if term_type == "summer_winter":
        db.flush()  # autoflush=False：学生记录需显式 flush 才可见，否则冲突检测漏检学生
        conflicts = check_term_conflicts(db, cls.id)
        if conflicts:
            db.rollback()
            raise HTTPException(status_code=400,
                                detail={"message": "班期存在时间冲突", "conflicts": conflicts})

    log_activity(db, "新建班级", f"班级「{cls.name}」")
    db.commit()
    db.refresh(cls)
    return success_response(_class_detail(db, cls))


@router.get("/{class_id}")
def get_class(class_id: int, db: Session = Depends(get_db)):
    """班级详情"""
    cls = db.query(Class).filter(Class.id == class_id).first()
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")
    return success_response(_class_detail(db, cls))


@router.put("/{class_id}")
def update_class(class_id: int, data: dict, db: Session = Depends(get_db)):
    """更新班级（名称/学科/教师/教室/班型/频率/时长/日期/备注）"""
    cls = db.query(Class).filter(Class.id == class_id).first()
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")
    if "name" in data and data["name"] is not None:
        cls.name = data["name"].strip()
    if "class_type" in data:
        if data["class_type"] not in ("1v1", "1vN"):
            raise HTTPException(status_code=400, detail="班型应为 1v1 或 1vN")
        if data["class_type"] == "1v1":
            cnt = db.query(ClassStudent).filter(ClassStudent.class_id == cls.id).count()
            if cnt > 1:
                raise HTTPException(status_code=400, detail="该班已有超过 1 名学生，无法改为一对一")
        cls.class_type = data["class_type"]
    # 整数字段归一化（前端表单可能传字符串，否则下游 int<str 比较 TypeError → 500）
    INT_FIELDS = {"total_lessons", "weekly_frequency", "duration_minutes"}
    for field in ["subject_id", "subject_name", "teacher_id", "classroom_id",
                  "term_type", "total_lessons", "daily_start", "daily_end",
                  "weekly_frequency", "duration_minutes", "start_date", "end_date", "notes"]:
        if field in data and data[field] is not None:
            setattr(cls, field, _to_int(data[field]) if field in INT_FIELDS else data[field])
    if cls.total_lessons is None:
        cls.total_lessons = 0

    # 寒暑假班：班期自动计算 + 冲突校验
    if cls.term_type == "summer_winter":
        if not cls.start_date or not cls.daily_start or not cls.daily_end or not cls.total_lessons:
            raise HTTPException(status_code=400, detail="寒暑假班需填写：开始日期、每天时段、总课次（天数）")
        cls.end_date = compute_end_date(cls.start_date, cls.total_lessons)
        db.flush()
        conflicts = check_term_conflicts(db, cls.id)
        if conflicts:
            db.rollback()
            raise HTTPException(status_code=400,
                                detail={"message": "班期存在时间冲突", "conflicts": conflicts})

    # 班级教师/教室变更后，同步该班 active 课次的冗余字段（否则冲突检测用旧教师/旧教室 → 误报/漏检）
    db.query(ClassSchedule).filter(
        ClassSchedule.class_id == cls.id,
        ClassSchedule.status == "active",
    ).update({"teacher_id": cls.teacher_id, "classroom_id": cls.classroom_id})

    cls.updated_at = now_iso()
    log_activity(db, "编辑班级", f"班级「{cls.name}」")
    db.commit()
    db.refresh(cls)
    return success_response(_class_detail(db, cls))


@router.put("/{class_id}/status")
def update_class_status(class_id: int, data: dict, db: Session = Depends(get_db)):
    """停用/启用班级"""
    cls = db.query(Class).filter(Class.id == class_id).first()
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")
    status = data.get("status", "")
    if status not in ("active", "paused"):
        raise HTTPException(status_code=400, detail="无效状态（应为 active 或 paused）")
    cls.status = status
    cls.updated_at = now_iso()
    label = "启用" if status == "active" else "停用"
    log_activity(db, f"{label}班级", f"班级「{cls.name}」")
    db.commit()
    return success_response(cls.to_dict())


@router.delete("/{class_id}")
def delete_class(class_id: int, db: Session = Depends(get_db)):
    """删除班级（级联删除关联的班级学生记录）"""
    cls = db.query(Class).filter(Class.id == class_id).first()
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")
    log_activity(db, "删除班级", f"班级「{cls.name}」")
    db.delete(cls)  # ClassStudent 通过 ondelete=CASCADE 一并清除
    db.commit()
    return success_response({"deleted": True})


@router.post("/{class_id}/students")
def add_student_to_class(class_id: int, data: dict, db: Session = Depends(get_db)):
    """向班级添加学生（唯一约束检查 + 返回该生现有在读班数供前端提示）"""
    cls = db.query(Class).filter(Class.id == class_id).first()
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")
    student_id = data.get("student_id")
    if not student_id:
        raise HTTPException(status_code=400, detail="缺少 student_id")
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")

    if cls.class_type == "1v1":
        cnt = db.query(ClassStudent).filter(ClassStudent.class_id == cls.id).count()
        if cnt >= 1:
            raise HTTPException(status_code=400, detail="一对一班级已有一名学生")

    exists = db.query(ClassStudent).filter(
        ClassStudent.class_id == cls.id,
        ClassStudent.student_id == student_id,
    ).first()
    if exists:
        raise HTTPException(status_code=400, detail="该学生已在班级中")

    # 冲突预检（P2 阶段）：该生当前在读班级数（P3 排课后将升级为时间冲突检测）
    active_classes = db.query(ClassStudent, Class).join(
        Class, ClassStudent.class_id == Class.id
    ).filter(
        ClassStudent.student_id == student_id,
        Class.status == "active",
    ).count()

    cs = ClassStudent(
        class_id=cls.id,
        student_id=student_id,
        subject_id=data.get("subject_id") or (cls.subject_id if cls.class_type == "1v1" else None),
    )
    db.add(cs)
    log_activity(db, "加入班级", f"{student.name} 加入班级「{cls.name}」", student_id=student_id)
    db.commit()
    db.refresh(cs)
    return success_response({
        "class_student": cs.to_dict(),
        "student_active_class_count": active_classes + 1,
    })


@router.delete("/{class_id}/students/{student_id}")
def remove_student_from_class(class_id: int, student_id: int, db: Session = Depends(get_db)):
    """从班级移除学生"""
    cs = db.query(ClassStudent).filter(
        ClassStudent.class_id == class_id,
        ClassStudent.student_id == student_id,
    ).first()
    if not cs:
        raise HTTPException(status_code=404, detail="该学生不在班级中")
    student = db.query(Student).filter(Student.id == student_id).first()
    cls = db.query(Class).filter(Class.id == class_id).first()
    log_activity(db, "移出班级", f"{student.name if student else ''} 移出班级「{cls.name if cls else ''}」",
                 student_id=student_id)
    db.delete(cs)
    db.commit()
    return success_response({"deleted": True})


@router.post("/{class_id}/extend")
def extend_class(class_id: int, data: dict, db: Session = Depends(get_db)):
    """寒暑假班续课：默认同时段追加天数；若续课后班期新增日期内该时段/教室被占用 → 报冲突提示重新排课"""
    cls = db.query(Class).filter(Class.id == class_id).first()
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")
    if cls.term_type != "summer_winter":
        raise HTTPException(status_code=400, detail="仅寒暑假班支持续课")

    new_total = int(data.get("new_total") or data.get("total_lessons") or 0)
    if new_total <= cls.total_lessons:
        return success_response({
            "extended": False,
            "message": f"续课后总课次需大于当前 {cls.total_lessons} 天（当前结束 {cls.end_date}）",
        })

    # 模拟续课：更新 total_lessons/end_date 后做班期冲突校验
    old_end = cls.end_date
    cls.total_lessons = new_total
    cls.end_date = compute_end_date(cls.start_date, new_total)
    db.flush()
    conflicts = check_term_conflicts(db, cls.id)
    if conflicts:
        db.rollback()
        return success_response({
            "extended": False,
            "conflicts": conflicts,
            "message": "续课后新增时段已被占用（教室/教师/学生冲突），需先重新排课",
        })

    cls.updated_at = now_iso()
    log_activity(db, "班级续课", f"班级「{cls.name}」续课至 {new_total} 次（结束 {cls.end_date}）")
    db.commit()
    db.refresh(cls)
    return success_response({
        "extended": True,
        "new_total": cls.total_lessons,
        "end_date": cls.end_date,
        "message": f"续课成功，总课次 {cls.total_lessons}，结束日期 {cls.end_date}",
    })


@router.post("/from-subject/{subject_id}")
def create_class_from_subject(subject_id: int, data: dict, db: Session = Depends(get_db)):
    """一对一快捷建班：把现有"学生+学科"升级为 1v1 班级"""
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="学科不存在")
    student = db.query(Student).filter(Student.id == subject.student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")

    # 幂等：该学科若已有 1v1 班级则返回现有班级
    existing = db.query(ClassStudent, Class).join(
        Class, ClassStudent.class_id == Class.id
    ).filter(
        ClassStudent.subject_id == subject_id,
        Class.class_type == "1v1",
        Class.status == "active",
    ).first()
    if existing:
        return success_response(_class_detail(db, existing[1]))

    cls = Class(
        name=data.get("name") or f"{student.name}·{subject.name}（一对一）",
        subject_id=subject_id,
        subject_name=subject.name,
        teacher_id=data.get("teacher_id"),
        classroom_id=data.get("classroom_id"),
        class_type="1v1",
        weekly_frequency=_to_int(data.get("weekly_frequency"), 2),
        duration_minutes=_to_int(data.get("duration_minutes"), 120),
        start_date=data.get("start_date", ""),
        end_date=data.get("end_date", ""),
    )
    db.add(cls)
    db.flush()
    db.add(ClassStudent(class_id=cls.id, student_id=student.id, subject_id=subject_id))
    log_activity(db, "新建班级", f"一对一班级「{cls.name}」", student_id=student.id, subject_id=subject_id)
    db.commit()
    db.refresh(cls)
    return success_response(_class_detail(db, cls))
