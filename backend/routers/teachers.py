"""
教师管理 API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.models import get_db
from backend.models.teacher import Teacher
from backend.utils.helpers import success_response, now_iso

router = APIRouter(prefix="/api/teachers", tags=["teachers"])


@router.get("")
def list_teachers(search: str = "", db: Session = Depends(get_db)):
    """教师列表"""
    query = db.query(Teacher)
    if search:
        query = query.filter(
            (Teacher.name.contains(search)) | (Teacher.subjects.contains(search))
        )
    teachers = query.order_by(Teacher.name).all()
    return success_response([t.to_dict() for t in teachers])


@router.post("")
def create_teacher(data: dict, db: Session = Depends(get_db)):
    """新增教师"""
    teacher = Teacher(
        name=data.get("name", ""),
        phone=data.get("phone", ""),
        subjects=data.get("subjects", ""),
        intro=data.get("intro", ""),
    )
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return success_response(teacher.to_dict())


@router.put("/{teacher_id}")
def update_teacher(teacher_id: int, data: dict, db: Session = Depends(get_db)):
    """编辑教师"""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="教师不存在")
    for field in ["name", "phone", "subjects", "intro"]:
        if field in data:
            setattr(teacher, field, data[field])
    teacher.updated_at = now_iso()
    db.commit()
    db.refresh(teacher)
    return success_response(teacher.to_dict())


@router.delete("/{teacher_id}")
def delete_teacher(teacher_id: int, db: Session = Depends(get_db)):
    """删除教师"""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="教师不存在")
    db.delete(teacher)
    db.commit()
    return success_response({"deleted": True})
