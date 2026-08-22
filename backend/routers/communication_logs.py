"""
沟通日志 API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.models import get_db
from backend.models.communication_log import CommunicationLog
from backend.utils.activity import log_activity
from backend.utils.helpers import success_response, now_iso

router = APIRouter(prefix="/api", tags=["communication_logs"])


@router.get("/subjects/{subject_id}/communication-logs")
def list_logs(subject_id: int, db: Session = Depends(get_db)):
    """日志列表"""
    logs = db.query(CommunicationLog).filter(
        CommunicationLog.subject_id == subject_id
    ).order_by(CommunicationLog.log_time.desc()).all()
    return success_response([l.to_dict() for l in logs])


@router.post("/subjects/{subject_id}/communication-logs")
def create_log(subject_id: int, data: dict, db: Session = Depends(get_db)):
    """新增日志"""
    from backend.models.subject import Subject
    if not db.query(Subject).filter(Subject.id == subject_id).first():
        raise HTTPException(status_code=404, detail="学科不存在")
    log = CommunicationLog(
        subject_id=subject_id,
        method=data.get("method", "面谈"),
        content=data.get("content", ""),
        log_time=data.get("log_time", now_iso()),
    )
    db.add(log)
    log_activity(db, "新增沟通日志", f"方式：{log.method}", subject_id=subject_id)
    db.commit()
    db.refresh(log)
    return success_response(log.to_dict())


@router.put("/communication-logs/{log_id}")
def update_log(log_id: int, data: dict, db: Session = Depends(get_db)):
    """编辑日志"""
    log = db.query(CommunicationLog).filter(CommunicationLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="日志不存在")
    for field in ["method", "content", "log_time"]:
        if field in data:
            setattr(log, field, data[field])
    log_activity(db, "编辑沟通日志", subject_id=log.subject_id)
    db.commit()
    db.refresh(log)
    return success_response(log.to_dict())


@router.delete("/communication-logs/{log_id}")
def delete_log(log_id: int, db: Session = Depends(get_db)):
    """删除日志"""
    log = db.query(CommunicationLog).filter(CommunicationLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="日志不存在")
    log_activity(db, "删除沟通日志", subject_id=log.subject_id)
    db.delete(log)
    db.commit()
    return success_response({"deleted": True})
