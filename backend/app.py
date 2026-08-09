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

    # 前端静态资源完全禁止缓存（no-store），避免浏览器用旧文件导致页面 JS 失效
    # no-cache 只要求"重新校验"，某些浏览器/场景仍会命中旧缓存，故升级为 no-store
    # 配合 index.html 里的版本自愈脚本，改代码后浏览器自动强制刷新，用户无需手动清缓存
    @app.middleware("http")
    async def no_cache_frontend(request, call_next):
        response = await call_next(request)
        path = request.url.path
        if (path in ("/", "/index.html")
                or path.endswith((".html", ".js", ".css"))
                or path.startswith(("/pages/", "/js/", "/css/", "/components/"))):
            response.headers["Cache-Control"] = "no-store"
        return response

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
    app.include_router(knowledge_base.qa_router)
    app.include_router(settings.router)
    app.include_router(dashboard.router)

    # 静态文件（前端）
    frontend_path = Path(FRONTEND_DIR)
    if frontend_path.exists():
        app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")

    # 启动时初始化数据库 + 自动备份（数据安全：保留最近 N 份，防止误删不可恢复）
    @app.on_event("startup")
    async def startup():
        init_db()
        from backend.utils.backup import backup_database  # 延迟导入避免循环
        try:
            backup_database()
        except Exception:
            pass  # 备份失败不阻塞启动

    return app


app = create_app()
