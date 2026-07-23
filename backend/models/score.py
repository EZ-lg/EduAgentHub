"""
考试成绩模型
"""
from sqlalchemy import Column, Integer, String, Float, ForeignKey, Text
from backend.models import Base
from backend.utils.helpers import now_iso


class Score(Base):
    __tablename__ = "scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    exam_name = Column(String, default="")
    score = Column(Float, nullable=False)
    total_score = Column(Float, nullable=False)
    exam_date = Column(String, nullable=False)
    notes = Column(Text, default="")
    created_at = Column(String, default=now_iso)

    def to_dict(self):
        return {
            "id": self.id,
            "subject_id": self.subject_id,
            "exam_name": self.exam_name,
            "score": self.score,
            "total_score": self.total_score,
            "exam_date": self.exam_date,
            "notes": self.notes,
            "created_at": self.created_at,
        }
