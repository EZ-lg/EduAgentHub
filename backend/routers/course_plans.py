"""
课程规划 API（P6 实现完整逻辑）
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.models import get_db
from backend.models.course_plan import CoursePlan
from backend.utils.helpers import success_response, now_iso

router = APIRouter(prefix="/api", tags=["course_plans"])


@router.get("/subjects/{subject_id}/plans")
def list_plans(subject_id: int, db: Session = Depends(get_db)):
    """规划列表"""
    plans = db.query(CoursePlan).filter(
        CoursePlan.subject_id == subject_id
    ).order_by(CoursePlan.version.desc()).all()
    return success_response([p.to_dict() for p in plans])


@router.post("/subjects/{subject_id}/plans")
def create_plan(subject_id: int, data: dict, db: Session = Depends(get_db)):
    """新建规划"""
    plan = CoursePlan(
        subject_id=subject_id,
        version=data.get("version", 1),
        plan_json=data.get("plan_json", "[]"),
        status=data.get("status", "active"),
        adjustment_reason=data.get("adjustment_reason", ""),
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return success_response(plan.to_dict())


@router.put("/plans/{plan_id}")
def update_plan(plan_id: int, data: dict, db: Session = Depends(get_db)):
    """编辑规划"""
    plan = db.query(CoursePlan).filter(CoursePlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="规划不存在")
    for field in ["plan_json", "status", "adjustment_reason"]:
        if field in data:
            setattr(plan, field, data[field])
    db.commit()
    db.refresh(plan)
    return success_response(plan.to_dict())


@router.get("/plans/{plan_id}/versions")
def plan_versions(plan_id: int, db: Session = Depends(get_db)):
    """版本历史"""
    plan = db.query(CoursePlan).filter(CoursePlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="规划不存在")
    # 同 subject 下所有版本
    versions = db.query(CoursePlan).filter(
        CoursePlan.subject_id == plan.subject_id
    ).order_by(CoursePlan.version.desc()).all()
    return success_response([v.to_dict() for v in versions])
