"""
课程规划模型
"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey
from backend.models import Base
from backend.utils.helpers import now_iso


class CoursePlan(Base):
    __tablename__ = "course_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, default=1)
    plan_json = Column(Text, default="[]")  # [{lesson, content, hours, teacher_id, schedule, notes}]
    status = Column(String, default="active")  # active / archived
    adjustment_reason = Column(String, default="")
    created_at = Column(String, default=now_iso)

    def to_dict(self):
        return {
            "id": self.id,
            "subject_id": self.subject_id,
            "version": self.version,
            "plan_json": self.plan_json,
            "status": self.status,
            "adjustment_reason": self.adjustment_reason,
            "created_at": self.created_at,
        }
