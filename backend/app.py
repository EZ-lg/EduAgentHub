"""
FastAPI 应用工厂
"""
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from backend.models import init_db
from backend.routers import (
    students, subjects, conversations, reports,
    scores, course_plans, communication_logs,
    teachers, knowledge_base, settings, dashboard
)
from config import FRONTEND_DIR


def create_app() -> FastAPI:
    app = FastAPI(
        title="教培智能体",
        description="教培机构一站式学员管理及AI助学工具",
        version="1.0.0"
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册 API 路由
    app.include_router(students.router)
    app.include_router(subjects.router)
    app.include_router(conversations.router)
    app.include_router(reports.router)
    app.include_router(scores.router)
    app.include_router(course_plans.router)
    app.include_router(communication_logs.router)
    app.include_router(teachers.router)
    app.include_router(knowledge_base.router)
    app.include_router(settings.router)
    app.include_router(dashboard.router)

    # 静态文件（前端）
    frontend_path = Path(FRONTEND_DIR)
    if frontend_path.exists():
        app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")

    # 启动时初始化数据库
    @app.on_event("startup")
    async def startup():
        init_db()

    return app


app = create_app()
