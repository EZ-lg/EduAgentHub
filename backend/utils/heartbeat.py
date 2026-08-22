"""
心跳超时自动退出 — 实现"关闭浏览器后后台自动退出"

原理：浏览器页面 JS 定时（30s）调 /api/app/heartbeat 刷新心跳；
守护线程每 15s 检查：若"收到过心跳"且超过 N 秒（默认 90s）再无心跳，
判定浏览器已关闭（标签 JS 停止运行），自动结束进程。

- 只在"收到过至少一次心跳"后才启用超时判定：测试/无浏览器场景永不误杀
- 开关与超时存在 settings 表（key=auto_exit，value_json={enabled, timeout}），
  设置页可关掉自动退出
"""
import json
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_state = {"last_heartbeat": None, "enabled": True, "timeout": 90}


def beat():
    """前端心跳：刷新最后活跃时间"""
    _state["last_heartbeat"] = time.time()


def _load_settings():
    """从 settings 表读取开关与超时（monitor 每次循环调用，配置即时生效）"""
    try:
        from backend.models import SessionLocal
        from backend.models.setting import Setting
        db = SessionLocal()
        try:
            s = db.query(Setting).filter(Setting.key == "auto_exit").first()
            cfg = json.loads(s.value_json) if s and s.value_json else {}
            _state["enabled"] = bool(cfg.get("enabled", True))
            _state["timeout"] = max(30, int(cfg.get("timeout", 90)))
        finally:
            db.close()
    except Exception:
        pass  # 读设置失败沿用当前值，不阻塞


def _monitor():
    while True:
        time.sleep(15)
        _load_settings()
        if not _state["enabled"]:
            continue
        last = _state["last_heartbeat"]
        if last is not None and (time.time() - last) > _state["timeout"]:
            logger.warning("浏览器已关闭（心跳超时 %ss），自动退出后台", _state["timeout"])
            os._exit(0)


def start_monitor():
    """启动守护线程（app startup 时调用一次，daemon 线程不阻塞退出）"""
    threading.Thread(target=_monitor, daemon=True).start()
