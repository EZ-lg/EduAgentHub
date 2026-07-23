"""
学生管理 API
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.models import get_db
from backend.models.student import Student
from backend.utils.helpers import success_response, error_response, now_iso

router = APIRouter(prefix="/api/students", tags=["students"])


@router.get("")
def list_students(
    search: str = "",
    grade: str = "",
    status: str = "",
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    """获取学生列表（搜索/筛选/分页）"""
    query = db.query(Student)
    if search:
        query = query.filter(
            (Student.name.contains(search)) | (Student.phone.contains(search))
        )
    if grade:
        query = query.filter(Student.grade == grade)
    if status:
        query = query.filter(Student.status == status)
    total = query.count()
    items = query.order_by(Student.updated_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return success_response({
        "items": [s.to_dict() for s in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.post("")
def create_student(data: dict, db: Session = Depends(get_db)):
    """新建学生"""
    student = Student(
        name=data.get("name", ""),
        gender=data.get("gender", ""),
        grade=data.get("grade", ""),
        school=data.get("school", ""),
        phone=data.get("phone", ""),
        parent_name=data.get("parent_name", ""),
        parent_phone=data.get("parent_phone", ""),
        address=data.get("address", ""),
        source=data.get("source", ""),
        notes=data.get("notes", ""),
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return success_response(student.to_dict())


@router.get("/{student_id}")
def get_student(student_id: int, db: Session = Depends(get_db)):
    """获取学生详情"""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    return success_response(student.to_dict())


@router.put("/{student_id}")
def update_student(student_id: int, data: dict, db: Session = Depends(get_db)):
    """更新学生信息"""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    for field in ["name", "gender", "grade", "school", "phone", "parent_name",
                  "parent_phone", "address", "source", "notes"]:
        if field in data:
            setattr(student, field, data[field])
    student.updated_at = now_iso()
    db.commit()
    db.refresh(student)
    return success_response(student.to_dict())


@router.delete("/{student_id}")
def delete_student(student_id: int, db: Session = Depends(get_db)):
    """删除学生（级联删除学科及关联数据）"""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    db.delete(student)
    db.commit()
    return success_response({"deleted": True})


@router.put("/{student_id}/status")
def update_student_status(student_id: int, data: dict, db: Session = Depends(get_db)):
    """更新学生状态"""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    status = data.get("status", "")
    if status not in ("active", "completed", "abandoned"):
        raise HTTPException(status_code=400, detail="无效状态")
    student.status = status
    student.updated_at = now_iso()
    db.commit()
    return success_response(student.to_dict())
