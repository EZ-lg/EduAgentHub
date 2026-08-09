"""
成绩管理 API（P6：单条/批量录入 + AI 成绩分析）
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.models import get_db
from backend.models.score import Score
from backend.models.subject import Subject
from backend.services import score_analyzer
from backend.utils.activity import log_activity
from backend.utils.helpers import success_response, now_iso

router = APIRouter(prefix="/api", tags=["scores"])

BATCH_MAX = 200


# ---------------------------------------------------------------- 私有工具

def _to_float(v, default=None):
    """转 float；None/'' 返回 default；非数字抛 400"""
    if v in (None, "", "null"):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"分数必须是数字，收到：{v}")


def _normalize_date(v) -> str:
    """日期归一化为 YYYY-MM-DD；空/无效 → 今天；保证 exam_date 字符串倒序排序正确"""
    if not v:
        return now_iso()[:10]
    text = str(v).strip()
    # 兼容 ISO（T 截断）与 / 分隔
    date_part = text.split("T")[0].split(" ")[0].replace("/", "-")
    try:
        return datetime.strptime(date_part, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"日期格式无效（应为 YYYY-MM-DD）：{text}")


def _validate_score_vals(score, total):
    if score is None or score < 0:
        raise HTTPException(status_code=400, detail="分数不能为负")
    if total is None or total <= 0:
        raise HTTPException(status_code=400, detail="满分必须大于 0")


def _subject_exists(db: Session, subject_id: int):
    if not db.get(Subject, subject_id):
        raise HTTPException(status_code=404, detail="学科不存在")


# ---------------------------------------------------------------- 接口

@router.get("/subjects/{subject_id}/scores")
def list_scores(subject_id: int, db: Session = Depends(get_db)):
    """成绩列表"""
    scores = db.query(Score).filter(
        Score.subject_id == subject_id
    ).order_by(Score.exam_date.desc()).all()
    return success_response([s.to_dict() for s in scores])


@router.post("/subjects/{subject_id}/scores")
def create_score(subject_id: int, data: dict, db: Session = Depends(get_db)):
    """录入单条成绩"""
    _subject_exists(db, subject_id)
    score_val = _to_float(data.get("score"), None)
    total_val = _to_float(data.get("total_score"), 100.0)
    _validate_score_vals(score_val, total_val)
    score = Score(
        subject_id=subject_id,
        exam_name=str(data.get("exam_name") or "").strip(),
        score=score_val,
        total_score=total_val,
        exam_date=_normalize_date(data.get("exam_date")),
        notes=str(data.get("notes") or ""),
    )
    db.add(score)
    log_activity(db, "录入成绩", f"「{score.exam_name or '考试'}」{score.score}分", subject_id=subject_id)
    db.commit()
    db.refresh(score)
    return success_response(score.to_dict())


@router.post("/subjects/{subject_id}/scores/batch")
def batch_create_scores(subject_id: int, data: dict, db: Session = Depends(get_db)):
    """批量录入成绩：body {items:[{exam_name,score,total_score,exam_date,notes}]}"""
    _subject_exists(db, subject_id)
    items = data.get("items") or []
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="items 不能为空")
    if len(items) > BATCH_MAX:
        raise HTTPException(status_code=400, detail=f"单次最多 {BATCH_MAX} 条")
    created = []
    for it in items:
        if not isinstance(it, dict):
            raise HTTPException(status_code=400, detail="items 元素必须是对象")
        score_val = _to_float(it.get("score"), None)
        total_val = _to_float(it.get("total_score"), 100.0)
        _validate_score_vals(score_val, total_val)
        created.append(Score(
            subject_id=subject_id,
            exam_name=str(it.get("exam_name") or "").strip(),
            score=score_val,
            total_score=total_val,
            exam_date=_normalize_date(it.get("exam_date")),
            notes=str(it.get("notes") or ""),
        ))
    db.add_all(created)
    log_activity(db, "批量录入成绩", f"共 {len(created)} 条", subject_id=subject_id)
    db.commit()
    return success_response({"inserted": len(created)})


@router.post("/subjects/{subject_id}/scores/analyze")
def analyze_scores(subject_id: int, db: Session = Depends(get_db)):
    """AI 成绩分析：趋势 + 薄弱点 + 与目标差距 + 建议 + 目标百分比"""
    result = score_analyzer.analyze_scores(db, subject_id)
    return success_response(result)


@router.put("/scores/{score_id}")
def update_score(score_id: int, data: dict, db: Session = Depends(get_db)):
    """编辑成绩"""
    score = db.query(Score).filter(Score.id == score_id).first()
    if not score:
        raise HTTPException(status_code=404, detail="成绩记录不存在")
    if "score" in data:
        score_val = _to_float(data.get("score"), None)
        total_val = _to_float(data.get("total_score"), score.total_score)
        _validate_score_vals(score_val, total_val)
        score.score = score_val
    if "total_score" in data:
        total_val = _to_float(data.get("total_score"), None)
        _validate_score_vals(score.score, total_val)
        score.total_score = total_val
    for field in ["exam_name", "notes"]:
        if field in data:
            setattr(score, field, data[field])
    if "exam_date" in data:
        score.exam_date = _normalize_date(data["exam_date"])
    log_activity(db, "编辑成绩", f"「{score.exam_name or '考试'}」", subject_id=score.subject_id)
    db.commit()
    db.refresh(score)
    return success_response(score.to_dict())


@router.delete("/scores/{score_id}")
def delete_score(score_id: int, db: Session = Depends(get_db)):
    """删除成绩"""
    score = db.query(Score).filter(Score.id == score_id).first()
    if not score:
        raise HTTPException(status_code=404, detail="成绩记录不存在")
    log_activity(db, "删除成绩", f"「{score.exam_name or '考试'}」", subject_id=score.subject_id)
    db.delete(score)
    db.commit()
    return success_response({"deleted": True})
