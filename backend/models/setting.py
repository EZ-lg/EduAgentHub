"""
系统设置模型
"""
from sqlalchemy import Column, Integer, String, Text
from backend.models import Base
from backend.utils.helpers import now_iso


class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String, nullable=False, unique=True)
    value_json = Column(Text, default="{}")
    updated_at = Column(String, default=now_iso)

    def to_dict(self):
        return {
            "id": self.id,
            "key": self.key,
            "value_json": self.value_json,
            "updated_at": self.updated_at,
        }
