"""
应用控制 API — 商用退出入口

解决桌面软件常见痛点：用户关掉浏览器窗口后，后端服务进程仍残留运行，
导致 exe 文件被锁定、无法删除/覆盖/更新。

- POST /exit      手动退出：延迟 1.5s 结束进程（先返回响应给前端提示）
- POST /heartbeat 浏览器心跳：页面 JS 定时刷新，供"关浏览器自动退出"判定
- GET/POST /auto-exit  读/写"关闭浏览器自动退出"设置（开关 + 超时）
"""
import json
import os
import threading

from fastapi import APIRouter

from backend.models import SessionLocal
from backend.models.setting import Setting
from backend.utils.helpers import now_iso, success_response

router = APIRouter(prefix="/api/app", tags=["app"])


@router.post("/exit")
def exit_app():
    """退出程序：延迟 1.5 秒结束进程，给前端时间展示"即将退出"提示"""
    def _kill():
        os._exit(0)  # 立即结束进程（uvicorn/threading 均不阻塞）；onefile 的 _MEI 临时目录残留无害
    threading.Timer(1.5, _kill).start()
    return success_response({"exiting": True, "message": "程序即将退出，浏览器页面将自动失效"})


@router.post("/heartbeat")
def heartbeat():
    """浏览器心跳：刷新最后活跃时间（页面 JS 每 30s 调用一次）"""
    from backend.utils.heartbeat import beat
    beat()
    return success_response({"ok": True})


@router.get("/auto-exit")
def get_auto_exit():
    """读取"关闭浏览器自动退出"设置"""
    s = SessionLocal().query(Setting).filter(Setting.key == "auto_exit").first()
    cfg = json.loads(s.value_json) if s and s.value_json else {}
    return success_response({"enabled": cfg.get("enabled", True), "timeout": cfg.get("timeout", 90)})


@router.post("/auto-exit")
def set_auto_exit(data: dict):
    """设置"关闭浏览器自动退出"：{enabled, timeout}"""
    try:
        timeout = max(30, int(data.get("timeout", 90)))
    except (TypeError, ValueError):
        timeout = 90
    db = SessionLocal()
    try:
        value = json.dumps({"enabled": bool(data.get("enabled", True)), "timeout": timeout},
                           ensure_ascii=False)
        s = db.query(Setting).filter(Setting.key == "auto_exit").first()
        if s:
            s.value_json = value
            s.updated_at = now_iso()
        else:
            db.add(Setting(key="auto_exit", value_json=value, updated_at=now_iso()))
        db.commit()
    finally:
        db.close()
    return success_response({"saved": True})
