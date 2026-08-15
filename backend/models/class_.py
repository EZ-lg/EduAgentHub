"""
班级模型（2.0 上课维度核心实体：一门课一个班）

双维度设计：
- 学习维度（subjects）：学生"学什么"的记录仓库，报告/规划/成绩/日志挂这里（1.0）
- 上课维度（classes）：机构"怎么上课"的排课单元（2.0），绑定学科/教师/教室/学生

班型：
- 1v1：班内 1 人（现有"学生+学科+教师"自动成班）
- 1vN：一对多小班，多学生
"""
from sqlalchemy import Column, Integer, String, ForeignKey, Text
from backend.models import Base
from backend.utils.helpers import now_iso


class Class(Base):
    __tablename__ = "classes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    subject_name = Column(String, default="")  # 学科名（1v1 与 subject_id 一致；1vN 班级用学科名）
    teacher_id = Column(Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True)
    classroom_id = Column(Integer, ForeignKey("classrooms.id", ondelete="SET NULL"), nullable=True)
    class_type = Column(String, default="1vN")  # 1v1 / 1vN
    weekly_frequency = Column(Integer, default=2)      # 每周课次
    duration_minutes = Column(Integer, default=120)    # 单次时长（分钟）
    start_date = Column(String, default="")
    end_date = Column(String, default="")
    status = Column(String, default="active")  # active / paused
    notes = Column(Text, default="")
    created_at = Column(String, default=now_iso)
    updated_at = Column(String, default=now_iso)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "subject_id": self.subject_id,
            "subject_name": self.subject_name,
            "teacher_id": self.teacher_id,
            "classroom_id": self.classroom_id,
            "class_type": self.class_type,
            "weekly_frequency": self.weekly_frequency,
            "duration_minutes": self.duration_minutes,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "status": self.status,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
