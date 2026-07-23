"""
成绩管理 API（P6 实现完整逻辑）
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.models import get_db
from backend.models.score import Score
from backend.utils.helpers import success_response, now_iso

router = APIRouter(prefix="/api", tags=["scores"])


@router.get("/subjects/{subject_id}/scores")
def list_scores(subject_id: int, db: Session = Depends(get_db)):
    """成绩列表"""
    scores = db.query(Score).filter(
        Score.subject_id == subject_id
    ).order_by(Score.exam_date.desc()).all()
    return success_response([s.to_dict() for s in scores])


@router.post("/subjects/{subject_id}/scores")
def create_score(subject_id: int, data: dict, db: Session = Depends(get_db)):
    """录入成绩"""
    score = Score(
        subject_id=subject_id,
        exam_name=data.get("exam_name", ""),
        score=data.get("score", 0),
        total_score=data.get("total_score", 100),
        exam_date=data.get("exam_date", now_iso()),
        notes=data.get("notes", ""),
    )
    db.add(score)
    db.commit()
    db.refresh(score)
    return success_response(score.to_dict())


@router.put("/scores/{score_id}")
def update_score(score_id: int, data: dict, db: Session = Depends(get_db)):
    """编辑成绩"""
    score = db.query(Score).filter(Score.id == score_id).first()
    if not score:
        raise HTTPException(status_code=404, detail="成绩记录不存在")
    for field in ["exam_name", "score", "total_score", "exam_date", "notes"]:
        if field in data:
            setattr(score, field, data[field])
    db.commit()
    db.refresh(score)
    return success_response(score.to_dict())


@router.delete("/scores/{score_id}")
def delete_score(score_id: int, db: Session = Depends(get_db)):
    """删除成绩"""
    score = db.query(Score).filter(Score.id == score_id).first()
    if not score:
        raise HTTPException(status_code=404, detail="成绩记录不存在")
    db.delete(score)
    db.commit()
    return success_response({"deleted": True})
