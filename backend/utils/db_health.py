"""
启动自检与自动修复 — 数据安全最后一道防线

check_and_repair_db() 必须在 init_db() 之前调用：
1. DB 不存在 → ok-new（首启，交给 init_db 建库）
2. quick_check 通过 → ok。缺表不算损坏（老版本升级缺新表是常态），交给 init_db 补建
3. quick_check 失败（真损坏）→ 损坏 DB 留证 quarantine/ → 找最近有效 .db 备份 → 在线恢复
   → 验证 → recovered（日志写明可能丢失最近一次备份后的数据）
4. 无可用备份或恢复后仍损坏 → fatal（写 data/startup_failed.txt + windowed 直接弹窗）

原则：能自动恢复到一份验证通过的库才自动恢复；否则宁可停，不可带伤运行。
不尝试二次自动恢复 —— 恢复出来的库仍损坏说明备份本身也坏了，必须人工介入。
"""
import logging
import os
import shutil
import sqlite3
import sys
from datetime import datetime

from config import DB_PATH, DATA_DIR, QUARANTINE_DIR

logger = logging.getLogger(__name__)

# 供 /api/settings/health 读取的健康快照（进程内内存态）
HEALTH = {
    "status": "unknown",          # ok | ok-new | recovered | fatal
    "checked_at": None,
    "message": "",
    "last_repair": None,
    "last_repair_message": "",
    "last_backup": None,
    "last_backup_at": None,
}

STARTUP_FAILED_TXT = os.path.join(DATA_DIR, "startup_failed.txt")


def expected_tables() -> list:
    """与 models.init_db 完全一致的业务表清单（新增表时需同步）"""
    from backend.models.student import Student  # noqa: F401
    from backend.models.subject import Subject  # noqa: F401
    from backend.models.ai_conversation import AIConversation  # noqa: F401
    from backend.models.report import Report  # noqa: F401
    from backend.models.score import Score  # noqa: F401
    from backend.models.course_plan import CoursePlan  # noqa: F401
    from backend.models.communication_log import CommunicationLog  # noqa: F401
    from backend.models.teacher import Teacher  # noqa: F401
    from backend.models.knowledge_doc import KnowledgeDoc  # noqa: F401
    from backend.models.qa_history import QaHistory  # noqa: F401
    from backend.models.setting import Setting  # noqa: F401
    from backend.models.activity_log import ActivityLog  # noqa: F401
    from backend.models.classroom import Classroom  # noqa: F401
    from backend.models.class_ import Class  # noqa: F401
    from backend.models.class_student import ClassStudent  # noqa: F401
    from backend.models.class_schedule import ClassSchedule  # noqa: F401
    from backend.models import Base
    return set(t.name for t in Base.metadata.sorted_tables)


def check_db_integrity(db_path: str = DB_PATH, deep: bool = True) -> dict:
    """独立只读连接做完整性检测（不经过 SQLAlchemy engine，避免锁/缓存干扰）。
    deep=True 跑全库 PRAGMA quick_check（启动自检用）；deep=False 仅探活（设置页 health 用，大库不阻塞）"""
    result = {
        "exists": os.path.exists(db_path),
        "size": os.path.getsize(db_path) if os.path.exists(db_path) else 0,
        "quick_check": None,
        "tables_ok": None,
        "error": None,
    }
    if not result["exists"]:
        return result
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
        try:
            if deep:
                qc = con.execute("PRAGMA quick_check").fetchone()[0]
                result["quick_check"] = qc
            else:
                # 轻量探活：能打开 + schema 可读即视为可读库（不跑全库扫描）
                con.execute("SELECT count(*) FROM sqlite_master").fetchone()
                result["quick_check"] = "ok"
            try:
                tables = {r[0] for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
            except Exception:
                tables = set()
            result["tables_ok"] = expected_tables() <= tables
        finally:
            con.close()
    except Exception as e:
        result["error"] = str(e)
    return result


def _backup_is_valid(path: str) -> bool:
    """备份文件是否可用（quick_check 通过）"""
    try:
        con = sqlite3.connect(path, timeout=10)
        try:
            return con.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        finally:
            con.close()
    except Exception:
        return False


def _find_recent_valid_backup() -> str:
    """按时间倒序找最近一份 quick_check 通过的 .db 备份（启动恢复只认纯 DB 备份）"""
    from backend.utils.backup import BACKUP_DIR, list_backups
    for item in list_backups():
        if not item["filename"].endswith(".db"):
            continue
        path = os.path.join(BACKUP_DIR, item["filename"])
        if _backup_is_valid(path):
            return path
    return ""


def quarantine_corrupt_db() -> str:
    """损坏 DB 留证到 quarantine/，返回证据路径。
    移动优先（源已不在 DB_PATH）；移动失败退化为复制后必须删除 DB_PATH，
    否则后续恢复写入损坏目标会失败（file is not a database）。"""
    os.makedirs(QUARANTINE_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(QUARANTINE_DIR, f"tutoring-corrupted-{ts}.db")
    try:
        shutil.move(DB_PATH, dest)
        return dest
    except OSError:
        try:
            shutil.copy2(DB_PATH, dest)
            try:
                os.remove(DB_PATH)
            except OSError:
                pass
            return dest
        except OSError:
            return ""


def _restore_from_backup(backup_path: str) -> bool:
    """在线恢复（唯一实现在 backup.restore_db_from_file，含 engine.dispose）"""
    from backend.utils.backup import restore_db_from_file
    return restore_db_from_file(backup_path)


def _write_startup_failed(msg: str):
    try:
        with open(STARTUP_FAILED_TXT, "w", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def clear_startup_failed():
    """启动成功且自检通过后清除旧失败标记（main.py 每次启动时调用）"""
    try:
        if os.path.exists(STARTUP_FAILED_TXT):
            os.remove(STARTUP_FAILED_TXT)
    except OSError:
        pass


def _popup(msg: str):
    """windowed exe 无控制台：直接弹系统对话框，避免静默闪退"""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, "教培智能体：数据异常", 0x10)  # MB_ICONERROR
        except Exception:
            pass


def check_and_repair_db() -> dict:
    """启动自检 + 自动修复主流程，返回 {status, message, backup_used?, quarantined?}"""
    from backend.utils.logging_setup import setup_logging
    setup_logging()

    global HEALTH
    HEALTH["checked_at"] = datetime.now().isoformat()

    # 1) 首启：DB 不存在，交给 init_db 建库
    if not os.path.exists(DB_PATH):
        HEALTH.update(status="ok-new", message="数据库不存在，首次启动将自动创建")
        clear_startup_failed()
        logger.info("启动自检: 数据库不存在（首启）")
        return {"status": "ok-new", "message": HEALTH["message"]}

    # 2) quick_check 通过 → 库结构有效（缺表不算损坏，交给 init_db 的 create_all 补齐）
    res = check_db_integrity()
    if res["error"] is None and res["quick_check"] == "ok":
        HEALTH.update(status="ok", message="数据库完整性正常")
        clear_startup_failed()
        if not res["tables_ok"]:
            logger.info("启动自检: 库缺新表，将在 init_db 阶段补齐")
        else:
            logger.info("启动自检: 数据库完整性正常")
        return {"status": "ok", "message": HEALTH["message"]}

    # 3) quick_check 失败 = 真损坏 → 自动恢复
    logger.warning("启动自检异常: quick_check=%s error=%s，开始自动恢复",
                   res["quick_check"], res["error"])
    quarantined = quarantine_corrupt_db()
    logger.info("损坏数据库已留证: %s", quarantined or "（留证失败）")

    backup_path = _find_recent_valid_backup()
    if backup_path and _restore_from_backup(backup_path):
        after = check_db_integrity()
        if after["error"] is None and after["quick_check"] == "ok":
            msg = f"数据库损坏已从备份 {os.path.basename(backup_path)} 自动恢复"
            HEALTH.update(
                status="recovered",
                message=msg,
                last_repair=datetime.now().isoformat(),
                last_repair_message=(
                    f"损坏 DB 已留证 {quarantined or '（失败）'}；"
                    f"从 {os.path.basename(backup_path)} 恢复，"
                    "可能丢失最近一次备份之后的改动"
                ),
            )
            clear_startup_failed()
            logger.warning("自动恢复成功: %s", HEALTH["last_repair_message"])
            return {"status": "recovered", "message": msg,
                    "backup_used": os.path.basename(backup_path),
                    "quarantined": quarantined}

    # 4) fatal：无可用备份或恢复后仍损坏
    msg = ("数据库损坏且无法自动恢复。损坏文件已留证到 data/quarantine/ 目录。"
           "请从 data/backups/ 手动恢复，或联系技术支持。")
    HEALTH.update(
        status="fatal",
        message=msg,
        last_repair=datetime.now().isoformat(),
        last_repair_message="自动恢复失败（无有效备份或备份同样损坏）",
    )
    logger.critical("启动自检 fatal: %s", msg)
    _write_startup_failed(msg)
    _popup(msg)
    return {"status": "fatal", "message": msg}
