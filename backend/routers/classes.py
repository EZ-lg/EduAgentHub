"""
班级管理 API（2.0 上课维度核心）

覆盖：班级 CRUD + 学生增减 + 一对一快捷建班 + 增学生冲突预检（P3 排课完整校验）
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from backend.models import get_db
from backend.models.class_ import Class
from backend.models.class_student import ClassStudent
from backend.models.student import Student
from backend.models.subject import Subject
from backend.models.teacher import Teacher
from backend.models.classroom import Classroom
from backend.utils.activity import log_activity
from backend.utils.helpers import success_response, now_iso

router = APIRouter(prefix="/api/classes", tags=["classes"])


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
def list_classes(status: str = "", subject_id: int = None, teacher_id: int = None,
                 search: str = "", db: Session = Depends(get_db)):
    """班级列表（筛选：状态/学科/教师/名称搜索），含人数与关联名称"""
    query = db.query(Class)
    if status in ("active", "paused"):
        query = query.filter(Class.status == status)
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

    cls = Class(
        name=name,
        subject_id=data.get("subject_id"),
        subject_name=data.get("subject_name", ""),
        teacher_id=data.get("teacher_id"),
        classroom_id=data.get("classroom_id"),
        class_type=class_type,
        weekly_frequency=data.get("weekly_frequency", 2),
        duration_minutes=data.get("duration_minutes", 120),
        start_date=data.get("start_date", ""),
        end_date=data.get("end_date", ""),
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
    for field in ["subject_id", "subject_name", "teacher_id", "classroom_id",
                  "weekly_frequency", "duration_minutes", "start_date", "end_date", "notes"]:
        if field in data and data[field] is not None:
            setattr(cls, field, data[field])
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
        weekly_frequency=data.get("weekly_frequency", 2),
        duration_minutes=data.get("duration_minutes", 120),
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
