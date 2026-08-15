"""
班级课次模型（2.0 排课结果：每周循环课表）

状态机：
- draft    ：候选方案（智能排课产出，待教务确认）
- active   ：已确认课表（正式生效，参与冲突检测）
- archived ：调整时归档旧版本
"""
from sqlalchemy import Column, Integer, String, ForeignKey
from backend.models import Base
from backend.utils.helpers import now_iso


class ClassSchedule(Base):
    __tablename__ = "class_schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    weekday = Column(Integer, nullable=False)     # 0=周一 ... 6=周日
    start_time = Column(String, default="")        # "HH:MM"
    end_time = Column(String, default="")          # "HH:MM"
    # 冗余存储教师/教室：冲突检测与课表查询免 join（实际以 classes 为准，可随班级变更调整）
    classroom_id = Column(Integer, ForeignKey("classrooms.id", ondelete="SET NULL"), nullable=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True)
    status = Column(String, default="active")      # draft / active / archived
    created_at = Column(String, default=now_iso)

    def to_dict(self):
        return {
            "id": self.id,
            "class_id": self.class_id,
            "weekday": self.weekday,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "classroom_id": self.classroom_id,
            "teacher_id": self.teacher_id,
            "status": self.status,
            "created_at": self.created_at,
        }
