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
    # 班型模式：semester=学期跟班（每周固定 N 次循环） / summer_winter=寒暑假班（每天固定 1 节，周日休息，总天数 N）
    term_type = Column(String, default="semester")
    total_lessons = Column(Integer, default=0)   # 寒暑假班总课次（天数）；学期班为 0
    daily_start = Column(String, default="")     # 寒暑假班每天固定开始时间 "HH:MM"
    daily_end = Column(String, default="")       # 寒暑假班每天固定结束时间 "HH:MM"
    weekly_frequency = Column(Integer, default=2)      # 学期班每周课次
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
            "term_type": self.term_type,
            "total_lessons": self.total_lessons,
            "daily_start": self.daily_start,
            "daily_end": self.daily_end,
            "weekly_frequency": self.weekly_frequency,
            "duration_minutes": self.duration_minutes,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "status": self.status,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
