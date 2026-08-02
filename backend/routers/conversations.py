"""
AI 对话采集 API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.models import get_db
from backend.models.ai_conversation import AIConversation
from backend.services import conversation_service
from backend.utils.helpers import success_response

router = APIRouter(prefix="/api", tags=["conversations"])


def _resolve_conversation_id(db: Session, subject_id: int, data: dict = None):
    """优先取 body 里的 conversation_id；缺省时兜底为该学科最新进行中会话"""
    if data and data.get("conversation_id"):
        return data["conversation_id"]
    conv = db.query(AIConversation).filter(
        AIConversation.subject_id == subject_id,
        AIConversation.status == "in_progress",
    ).order_by(AIConversation.updated_at.desc()).first()
    return conv.id if conv else None


@router.post("/subjects/{subject_id}/conversation/start")
def start_conversation(subject_id: int, db: Session = Depends(get_db)):
    """开始（或恢复）一次 AI 对话采集，返回会话 + 是否已配置 + 学科/学生信息"""
    return success_response(conversation_service.start_conversation(db, subject_id))


@router.post("/subjects/{subject_id}/conversation/message")
def send_message(subject_id: int, data: dict, db: Session = Depends(get_db)):
    """发送消息 → AI 回复 + 是否该结束（should_end）+ 权威消息数组"""
    conv_id = _resolve_conversation_id(db, subject_id, data)
    if not conv_id:
        raise HTTPException(status_code=400, detail="缺少 conversation_id 且无进行中的会话")
    result = conversation_service.handle_message(
        db, subject_id, conv_id, (data or {}).get("message", ""))
    return success_response(result)


@router.post("/subjects/{subject_id}/conversation/end")
def end_conversation(subject_id: int, data: dict = None, db: Session = Depends(get_db)):
    """手动结束对话 → 生成学情总结（report_id 留待 P5）"""
    conv_id = _resolve_conversation_id(db, subject_id, data)
    if not conv_id:
        raise HTTPException(status_code=400, detail="缺少 conversation_id 且无进行中的会话")
    return success_response(conversation_service.end_conversation(db, subject_id, conv_id))


@router.get("/subjects/{subject_id}/conversations")
def list_conversations(subject_id: int, db: Session = Depends(get_db)):
    """历史对话列表（messages 为解析后的数组）"""
    conversations = db.query(AIConversation).filter(
        AIConversation.subject_id == subject_id
    ).order_by(AIConversation.created_at.desc()).all()
    return success_response([
        conversation_service.conversation_to_dict(c) for c in conversations
    ])
