"""
沟通日志模型
"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey
from backend.models import Base
from backend.utils.helpers import now_iso


class CommunicationLog(Base):
    __tablename__ = "communication_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    method = Column(String, default="面谈")  # 电话/微信/面谈/其他
    content = Column(Text, nullable=False)
    log_time = Column(String, nullable=False)
    created_at = Column(String, default=now_iso)

    def to_dict(self):
        return {
            "id": self.id,
            "subject_id": self.subject_id,
            "method": self.method,
            "content": self.content,
            "log_time": self.log_time,
            "created_at": self.created_at,
        }
