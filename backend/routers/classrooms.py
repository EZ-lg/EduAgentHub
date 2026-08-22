"""
教室管理 API（2.0 排课资源）
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.models import get_db
from backend.models.classroom import Classroom
from backend.models.class_ import Class
from backend.utils.activity import log_activity
from backend.utils.helpers import success_response, now_iso

router = APIRouter(prefix="/api/classrooms", tags=["classrooms"])


def _to_int(value, default=0):
    """安全转 int：非数字/非法返回 default（防 capacity 存成字符串导致排课比较 TypeError）"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@router.get("")
def list_classrooms(status: str = "", db: Session = Depends(get_db)):
    """教室列表（可按状态筛选 active/paused）"""
    query = db.query(Classroom)
    if status in ("active", "paused"):
        query = query.filter(Classroom.status == status)
    classrooms = query.order_by(Classroom.name).all()
    return success_response([c.to_dict() for c in classrooms])


@router.post("")
def create_classroom(data: dict, db: Session = Depends(get_db)):
    """新建教室"""
    capacity = _to_int(data.get("capacity"), 10)
    if capacity < 0:
        raise HTTPException(status_code=400, detail="教室容量不能为负")
    classroom = Classroom(
        name=data.get("name", ""),
        capacity=capacity,
        location=data.get("location", ""),
        notes=data.get("notes", ""),
        status=data.get("status", "active"),
    )
    if not classroom.name.strip():
        raise HTTPException(status_code=400, detail="教室名称不能为空")
    db.add(classroom)
    db.flush()
    log_activity(db, "新增教室", f"教室「{classroom.name}」")
    db.commit()
    db.refresh(classroom)
    return success_response(classroom.to_dict())


@router.put("/{classroom_id}")
def update_classroom(classroom_id: int, data: dict, db: Session = Depends(get_db)):
    """编辑教室"""
    classroom = db.query(Classroom).filter(Classroom.id == classroom_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="教室不存在")
    for field in ["name", "location", "notes", "status"]:
        if field in data and data[field] is not None:
            setattr(classroom, field, data[field])
    if "capacity" in data and data["capacity"] is not None:
        classroom.capacity = _to_int(data["capacity"], classroom.capacity)
    classroom.updated_at = now_iso()
    log_activity(db, "编辑教室", f"教室「{classroom.name}」")
    db.commit()
    db.refresh(classroom)
    return success_response(classroom.to_dict())


@router.delete("/{classroom_id}")
def delete_classroom(classroom_id: int, db: Session = Depends(get_db)):
    """删除教室（有班级引用时阻止，避免遗留无效引用）"""
    classroom = db.query(Classroom).filter(Classroom.id == classroom_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="教室不存在")
    refs = db.query(Class).filter(Class.classroom_id == classroom_id).count()
    if refs > 0:
        raise HTTPException(status_code=400, detail=f"该教室仍被 {refs} 个班级引用，请先调整班级教室")
    log_activity(db, "删除教室", f"教室「{classroom.name}」")
    db.delete(classroom)
    db.commit()
    return success_response({"deleted": True})
