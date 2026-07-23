"""
AI 对话记录模型
"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey
from backend.models import Base
from backend.utils.helpers import now_iso


class AIConversation(Base):
    __tablename__ = "ai_conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    messages_json = Column(Text, default="[]")  # [{role, content, time}, ...]
    status = Column(String, default="in_progress")  # in_progress / completed
    created_at = Column(String, default=now_iso)
    updated_at = Column(String, default=now_iso)

    def to_dict(self):
        return {
            "id": self.id,
            "subject_id": self.subject_id,
            "messages_json": self.messages_json,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
