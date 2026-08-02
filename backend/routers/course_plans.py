"""
课程规划 API（P6：手动保存新版本 + AI 调整建议）
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.models import get_db
from backend.models.course_plan import CoursePlan
from backend.services import score_analyzer
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
    """新建规划（等价 /plans/save：自动版本号 + 归档旧 active，避免版本纪律旁路）"""
    plan_rows = data.get("plan_json") or []
    if not isinstance(plan_rows, list):
        raise HTTPException(status_code=400, detail="plan_json 必须是数组")
    plan = score_analyzer.save_plan_version(
        db, subject_id, plan_rows, str(data.get("adjustment_reason") or "").strip())
    return success_response(plan)


@router.post("/subjects/{subject_id}/plans/save")
def save_plan(subject_id: int, data: dict, db: Session = Depends(get_db)):
    """手动保存课程规划为新版本（归档旧 active）：body {plan_json: [...], adjustment_reason: ""}"""
    plan_rows = data.get("plan_json") or []
    if not isinstance(plan_rows, list):
        raise HTTPException(status_code=400, detail="plan_json 必须是数组")
    plan = score_analyzer.save_plan_version(
        db, subject_id, plan_rows, str(data.get("adjustment_reason") or "").strip())
    return success_response(plan)


@router.post("/subjects/{subject_id}/plans/adjust")
def adjust_plan(subject_id: int, db: Session = Depends(get_db)):
    """AI 课程调整建议（预览不落库）：基于成绩分析返回调整后规划 + 原因"""
    result = score_analyzer.adjust_plan_preview(db, subject_id)
    return success_response(result)


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
