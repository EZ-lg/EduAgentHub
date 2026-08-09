"""
知识库问答历史模型（加分2：跨会话持久化）
"""
import json

from sqlalchemy import Column, Integer, String, Text
from backend.models import Base
from backend.utils.helpers import now_iso


class QaHistory(Base):
    __tablename__ = "qa_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question = Column(String, nullable=False)
    answer = Column(Text, default="")
    references_json = Column(Text, default="[]")
    created_at = Column(String, default=now_iso)

    def to_dict(self):
        try:
            refs = json.loads(self.references_json or "[]")
        except (json.JSONDecodeError, TypeError):
            refs = []
        return {
            "id": self.id,
            "question": self.question,
            "answer": self.answer,
            "references": refs if isinstance(refs, list) else [],
            "created_at": self.created_at,
        }
