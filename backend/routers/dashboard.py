"""
工作台 API
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.models import get_db
from backend.models.student import Student
from backend.models.subject import Subject
from backend.models.activity_log import ActivityLog
from backend.utils.helpers import success_response

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """统计卡片"""
    active_students = db.query(Student).filter(Student.status == "active").count()
    active_subjects = db.query(Subject).filter(Subject.status == "active").count()
    new_students = db.query(Student).filter(Student.status == "active").count()  # P9 实现本月新增
    total_students = db.query(Student).count()
    return success_response({
        "active_students": active_students,
        "active_subjects": active_subjects,
        "new_students_this_month": new_students,
        "total_students": total_students,
    })


@router.get("/activities")
def get_activities(page: int = 1, page_size: int = 20, db: Session = Depends(get_db)):
    """最近活动"""
    activities = db.query(ActivityLog).order_by(
        ActivityLog.created_at.desc()
    ).offset((page - 1) * page_size).limit(page_size).all()
    return success_response([a.to_dict() for a in activities])
