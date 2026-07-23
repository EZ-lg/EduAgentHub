"""
学生模型
"""
from sqlalchemy import Column, Integer, String, Text
from backend.models import Base
from backend.utils.helpers import now_iso


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    gender = Column(String, default="")
    grade = Column(String, default="")
    school = Column(String, default="")
    phone = Column(String, default="")
    parent_name = Column(String, default="")
    parent_phone = Column(String, default="")
    address = Column(String, default="")
    source = Column(String, default="")
    status = Column(String, default="active")  # active / completed / abandoned
    notes = Column(Text, default="")
    created_at = Column(String, default=now_iso)
    updated_at = Column(String, default=now_iso)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "gender": self.gender,
            "grade": self.grade,
            "school": self.school,
            "phone": self.phone,
            "parent_name": self.parent_name,
            "parent_phone": self.parent_phone,
            "address": self.address,
            "source": self.source,
            "status": self.status,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
