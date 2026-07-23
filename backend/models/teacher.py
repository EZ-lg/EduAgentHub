"""
教师模型
"""
from sqlalchemy import Column, Integer, String, Text
from backend.models import Base
from backend.utils.helpers import now_iso


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    phone = Column(String, default="")
    subjects = Column(String, default="")  # JSON数组：["数学","物理"]
    intro = Column(Text, default="")
    created_at = Column(String, default=now_iso)
    updated_at = Column(String, default=now_iso)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "subjects": self.subjects,
            "intro": self.intro,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
