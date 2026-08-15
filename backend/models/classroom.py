"""
教室模型（2.0 排课资源）
"""
from sqlalchemy import Column, Integer, String, Text
from backend.models import Base
from backend.utils.helpers import now_iso


class Classroom(Base):
    __tablename__ = "classrooms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    capacity = Column(Integer, default=10)   # 容量（人），排课时教室容量 ≥ 班级人数
    location = Column(String, default="")
    notes = Column(Text, default="")
    status = Column(String, default="active")  # active / paused
    created_at = Column(String, default=now_iso)
    updated_at = Column(String, default=now_iso)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "capacity": self.capacity,
            "location": self.location,
            "notes": self.notes,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
