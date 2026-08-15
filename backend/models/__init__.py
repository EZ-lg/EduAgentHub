"""
数据库初始化与 Session 管理
（方言细节已收敛到 backend/utils/db.py，ORM 层不出现 SQLite/PostgreSQL 差异）
"""
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from backend.utils.db import create_app_engine, run_light_migrations
from config import DATABASE_URL

engine = create_app_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


# 轻量列迁移规则：create_all 不会为已有表加新列，补齐历史列
# （新增列时在此登记：{表名: {"cols": {列名: DDL类型}}})
MIGRATION_RULES = {
    "knowledge_docs": {
        "cols": {
            "index_status": "VARCHAR DEFAULT 'done'",
            "index_error": "VARCHAR DEFAULT ''",
        }
    },
}


def init_db():
    """创建所有表 + 轻量列迁移"""
    from backend.models.student import Student
    from backend.models.subject import Subject
    from backend.models.ai_conversation import AIConversation
    from backend.models.report import Report
    from backend.models.score import Score
    from backend.models.course_plan import CoursePlan
    from backend.models.communication_log import CommunicationLog
    from backend.models.teacher import Teacher
    from backend.models.knowledge_doc import KnowledgeDoc
    from backend.models.qa_history import QaHistory
    from backend.models.setting import Setting
    from backend.models.activity_log import ActivityLog
    Base.metadata.create_all(bind=engine)
    run_light_migrations(engine, MIGRATION_RULES)


def get_db():
    """FastAPI 依赖注入：获取数据库 session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
