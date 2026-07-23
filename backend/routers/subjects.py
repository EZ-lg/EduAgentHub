"""
学科管理 API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.models import get_db
from backend.models.subject import Subject
from backend.utils.helpers import success_response, now_iso

router = APIRouter(prefix="/api", tags=["subjects"])


@router.get("/students/{student_id}/subjects")
def list_subjects(student_id: int, db: Session = Depends(get_db)):
    """获取某学生的学科列表"""
    subjects = db.query(Subject).filter(
        Subject.student_id == student_id
    ).order_by(Subject.created_at.desc()).all()
    return success_response([s.to_dict() for s in subjects])


@router.post("/subjects")
def create_subject(data: dict, db: Session = Depends(get_db)):
    """新增学科"""
    subject = Subject(
        student_id=data.get("student_id"),
        name=data.get("name", ""),
        status=data.get("status", "active"),
    )
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return success_response(subject.to_dict())


@router.get("/subjects/{subject_id}")
def get_subject(subject_id: int, db: Session = Depends(get_db)):
    """获取学科详情"""
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="学科不存在")
    return success_response(subject.to_dict())


@router.put("/subjects/{subject_id}")
def update_subject(subject_id: int, data: dict, db: Session = Depends(get_db)):
    """更新学科"""
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="学科不存在")
    if "name" in data:
        subject.name = data["name"]
    subject.updated_at = now_iso()
    db.commit()
    db.refresh(subject)
    return success_response(subject.to_dict())


@router.put("/subjects/{subject_id}/status")
def update_subject_status(subject_id: int, data: dict, db: Session = Depends(get_db)):
    """停用/启用学科"""
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="学科不存在")
    status = data.get("status", "")
    if status not in ("active", "paused"):
        raise HTTPException(status_code=400, detail="无效状态（应为 active 或 paused）")
    subject.status = status
    subject.updated_at = now_iso()
    db.commit()
    return success_response(subject.to_dict())
