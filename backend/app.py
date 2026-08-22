"""
FastAPI 应用工厂
"""
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

from backend.models import init_db
from backend.routers import (
    students, subjects, conversations, reports,
    scores, course_plans, communication_logs,
    teachers, knowledge_base, settings, dashboard,
    classes, classrooms, schedules, overview
)
from config import FRONTEND_DIR


def create_app() -> FastAPI:
    app = FastAPI(
        title="教培智能体",
        description="教培机构一站式学员管理及AI助学工具",
        version="2.0.0"
    )

    # CORS：本地单机同源访问，无需放开跨源。服务器部署走 nginx 同源反代，同样不需要。
    # 收紧为仅本机回环地址，杜绝恶意网页 drive-by 调用本地 API 覆写数据。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1", "http://localhost"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # CSRF 防线：写请求（POST/PUT/DELETE）若带 Origin 头且与请求 Host 不同源 → 拒绝。
    # multipart 上传是 CORS 安全清单内类型不触发预检，仅靠 CORS 挡不住，必须显式校验 Origin。
    @app.middleware("http")
    async def csrf_origin_check(request, call_next):
        if request.method in ("POST", "PUT", "DELETE"):
            origin = request.headers.get("origin", "")
            host = request.headers.get("host", "")
            if origin:
                from urllib.parse import urlparse
                o_host = urlparse(origin).netloc
                if o_host and o_host != host:
                    return JSONResponse(
                        {"success": False, "error": "跨源请求被拒绝"}, status_code=403)
        return await call_next(request)

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

    # 外键/唯一约束违规 → 400（兜住所有"引用不存在的 ID"请求，避免 500 泄漏堆栈）
    @app.exception_handler(IntegrityError)
    async def _integrity_handler(request: Request, exc: IntegrityError):
        logger.warning("IntegrityError on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            {"success": False, "error": "数据引用无效或已存在"}, status_code=400)

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
    app.include_router(classes.router)
    app.include_router(classrooms.router)
    app.include_router(schedules.router)
    app.include_router(overview.router)

    # 静态文件（前端）
    frontend_path = Path(FRONTEND_DIR)
    if frontend_path.exists():
        app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")

    # P0 数据可靠性启动序：日志 → 自检/自动修复 → 建表迁移 → 自动备份
    @app.on_event("startup")
    async def startup():
        from backend.utils.logging_setup import setup_logging
        setup_logging()
        from backend.utils.db_health import check_and_repair_db
        result = check_and_repair_db()
        if result["status"] == "fatal":
            # 数据库损坏且无法自动恢复：弹窗告知用户（windowed 无控制台，不能静默闪退），
            # 然后阻止启动，绝不在坏库上继续写
            from backend.utils.db_health import _popup
            _popup(result["message"])
            raise RuntimeError(result["message"])
        init_db()
        # 建表/迁移成功后清除历史启动失败标记，避免手动恢复后仍被旧标记挡住
        from backend.utils.db_health import clear_startup_failed
        clear_startup_failed()
        from backend.utils.backup import backup_database  # 延迟导入避免循环
        try:
            backup_database()
        except Exception:
            pass  # 备份失败不阻塞启动

    return app


app = create_app()
