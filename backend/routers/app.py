"""
应用控制 API — 商用退出入口

解决桌面软件常见痛点：用户关掉浏览器窗口后，后端服务进程仍残留运行，
导致 exe 文件被锁定、无法删除/覆盖/更新。

点击界面「退出程序」→ 后端延迟 1.5s 结束进程（先返回响应给前端提示），
进程退出后浏览器页面自然失效（localhost 拒绝连接），exe 文件即可安全删除。
"""
import os
import threading

from fastapi import APIRouter

from backend.utils.helpers import success_response

router = APIRouter(prefix="/api/app", tags=["app"])


@router.post("/exit")
def exit_app():
    """退出程序：延迟 1.5 秒结束进程，给前端时间展示"即将退出"提示"""
    def _kill():
        os._exit(0)  # 立即结束进程（uvicorn/threading 均不阻塞）；onefile 的 _MEI 临时目录残留无害
    threading.Timer(1.5, _kill).start()
    return success_response({"exiting": True, "message": "程序即将退出，浏览器页面将自动失效"})
