"""
应用日志设施 — 数据安全排查的暗线

PyInstaller windowed 模式无控制台（stdout/stderr 被 main.py 替换为 devnull），
文件日志是唯一可靠的排查通道。启动自检 / 自动恢复 / 迁移事件都写这里。

- root logger 挂 RotatingFileHandler → data/logs/app.log（2MB × 5 滚动）
- 幂等初始化：重复调用不叠加 handler（uvicorn reload / 多次 startup 安全）
"""
import logging
import os
from logging.handlers import RotatingFileHandler

from config import LOG_FILE, LOG_DIR

_initialized = False


def setup_logging() -> None:
    """初始化文件日志（幂等，重复调用无害）"""
    global _initialized
    if _initialized:
        return
    os.makedirs(LOG_DIR, exist_ok=True)
    handler = RotatingFileHandler(
        LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    ))
    root = logging.getLogger()
    # root 只放行 WARNING+，挡掉 uvicorn 访问日志等第三方 INFO 噪音
    root.setLevel(logging.WARNING)
    root.addHandler(handler)
    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """获取带文件日志的 logger（业务日志显式 INFO 级，可写入文件）"""
    setup_logging()
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    return logger
