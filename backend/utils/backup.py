"""
数据库自动备份 — 数据安全底裤

- 启动时自动备份 data/tutoring.db → data/backups/tutoring-YYYYMMDD-HHMMSS.db
- 用 sqlite3 backup API 在线备份，保证一致性（不用文件复制，避免写时损坏）
- 保留最近 MAX_BACKUPS 份，自动清理更旧的
- 提供 list_backups / backup_now 供设置页「数据管理」调用
"""
import glob
import os
import shutil
import sqlite3
from datetime import datetime

from config import DB_PATH, DATA_DIR

BACKUP_DIR = os.path.join(DATA_DIR, "backups")
MAX_BACKUPS = 14
GLOB_PATTERN = "tutoring-*.db"


def _ensure_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)


def backup_database() -> str:
    """执行一次备份，返回备份文件路径；失败返回 None（不抛异常，不阻塞启动）"""
    _ensure_dir()
    if not os.path.exists(DB_PATH):
        return None
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(BACKUP_DIR, f"tutoring-{ts}.db")
    try:
        src = sqlite3.connect(DB_PATH)
        dst = sqlite3.connect(dest)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
    except Exception:
        # 兜底：直接文件复制（极端情况下即使不一致也比没有强）
        try:
            shutil.copy2(DB_PATH, dest)
        except Exception:
            return None
    _prune()
    return dest


def list_backups() -> list:
    """列出全部备份：[{filename, size, created_at}]，按时间倒序"""
    _ensure_dir()
    files = sorted(glob.glob(os.path.join(BACKUP_DIR, GLOB_PATTERN)), reverse=True)
    result = []
    for f in files:
        try:
            size = os.path.getsize(f)
            mtime = datetime.fromtimestamp(os.path.getmtime(f))
        except OSError:
            continue
        result.append({
            "filename": os.path.basename(f),
            "size": size,
            "created_at": mtime.strftime("%Y-%m-%d %H:%M:%S"),
        })
    return result


def _prune():
    """保留最近 MAX_BACKUPS 份，删除更旧的"""
    files = sorted(glob.glob(os.path.join(BACKUP_DIR, GLOB_PATTERN)))
    for f in files[:-MAX_BACKUPS]:
        try:
            os.remove(f)
        except OSError:
            pass
