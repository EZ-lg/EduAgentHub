"""
数据库初始化与 Session 管理
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db():
    """创建所有表"""
    from backend.models.student import Student
    from backend.models.subject import Subject
    from backend.models.ai_conversation import AIConversation
    from backend.models.report import Report
    from backend.models.score import Score
    from backend.models.course_plan import CoursePlan
    from backend.models.communication_log import CommunicationLog
    from backend.models.teacher import Teacher
    from backend.models.knowledge_doc import KnowledgeDoc
    from backend.models.setting import Setting
    from backend.models.activity_log import ActivityLog
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI 依赖注入：获取数据库 session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
