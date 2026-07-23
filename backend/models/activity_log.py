"""
操作日志模型
"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey
from backend.models import Base
from backend.utils.helpers import now_iso


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="SET NULL"), nullable=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    action = Column(String, nullable=False)
    detail = Column(Text, default="")
    created_at = Column(String, default=now_iso)

    def to_dict(self):
        return {
            "id": self.id,
            "student_id": self.student_id,
            "subject_id": self.subject_id,
            "action": self.action,
            "detail": self.detail,
            "created_at": self.created_at,
        }
