"""
AI 对话 API（P4 实现完整逻辑）
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.models import get_db
from backend.models.ai_conversation import AIConversation
from backend.utils.helpers import success_response, now_iso

router = APIRouter(prefix="/api", tags=["conversations"])


@router.post("/subjects/{subject_id}/conversation/start")
def start_conversation(subject_id: int, data: dict = None, db: Session = Depends(get_db)):
    """开始新对话"""
    conversation = AIConversation(
        subject_id=subject_id,
        messages_json="[]",
        status="in_progress",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return success_response(conversation.to_dict())


@router.post("/subjects/{subject_id}/conversation/message")
def send_message(subject_id: int, data: dict, db: Session = Depends(get_db)):
    """发送消息（P4 实现 AI 回复逻辑）"""
    conversation_id = data.get("conversation_id")
    if not conversation_id:
        raise HTTPException(status_code=400, detail="缺少 conversation_id")
    return success_response({
        "conversation_id": conversation_id,
        "reply": "（AI 服务未配置，请先在设置中配置 LLM）",
        "should_end": False,
        "summary": None,
    })


@router.post("/subjects/{subject_id}/conversation/end")
def end_conversation(subject_id: int, data: dict = None, db: Session = Depends(get_db)):
    """手动结束对话（P4 实现完整逻辑）"""
    return success_response({
        "conversation_id": data.get("conversation_id") if data else None,
        "summary": "对话已结束",
        "report_id": None,
    })


@router.get("/subjects/{subject_id}/conversations")
def list_conversations(subject_id: int, db: Session = Depends(get_db)):
    """历史对话列表"""
    conversations = db.query(AIConversation).filter(
        AIConversation.subject_id == subject_id
    ).order_by(AIConversation.created_at.desc()).all()
    return success_response([c.to_dict() for c in conversations])
