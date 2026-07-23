"""
报告模型
"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey
from backend.models import Base
from backend.utils.helpers import now_iso


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    conversation_id = Column(Integer, ForeignKey("ai_conversations.id", ondelete="SET NULL"), nullable=True)
    title = Column(String, default="")
    content_json = Column(Text, default="{}")  # {sections: {...}}
    course_plan_id = Column(Integer, ForeignKey("course_plans.id", ondelete="SET NULL"), nullable=True)
    kb_references_json = Column(Text, default="[]")
    status = Column(String, default="draft")  # draft / published
    created_at = Column(String, default=now_iso)
    updated_at = Column(String, default=now_iso)

    def to_dict(self):
        return {
            "id": self.id,
            "subject_id": self.subject_id,
            "conversation_id": self.conversation_id,
            "title": self.title,
            "content_json": self.content_json,
            "course_plan_id": self.course_plan_id,
            "kb_references_json": self.kb_references_json,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
