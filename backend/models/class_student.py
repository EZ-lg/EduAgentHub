"""
班级-学生关联模型（一个学生可报多个班，一个班可有多名学生）
"""
from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint
from backend.models import Base
from backend.utils.helpers import now_iso


class ClassStudent(Base):
    __tablename__ = "class_students"
    __table_args__ = (
        UniqueConstraint("class_id", "student_id", name="uq_class_student"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    # 该生在该班对应的学科学习记录（一对一自动填；小班可空，报班后各自建学科记录）
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    enroll_date = Column(String, default=now_iso)
    status = Column(String, default="active")  # active

    def to_dict(self):
        return {
            "id": self.id,
            "class_id": self.class_id,
            "student_id": self.student_id,
            "subject_id": self.subject_id,
            "enroll_date": self.enroll_date,
            "status": self.status,
        }
