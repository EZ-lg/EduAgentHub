"""
数据库自动备份 — 数据安全底裤（P0 数据可靠性扩展）

- 启动/手动备份 data/tutoring.db → data/backups/tutoring-YYYYMMDD-HHMMSS.db
  用 sqlite3 backup API 在线备份，保证一致性（不用文件复制，避免写时损坏）
- full=True 生成 tutoring-full-*.zip：DB 在线快照 + uploads/ + chroma_data/ + exports/ + MANIFEST.json
- 保留最近 MAX_BACKUPS 份（.db 与 .zip 合并按修改时间排序）
- 提供 list_backups / delete_backup / restore_database / restore_db_from_file
  供设置页「数据管理」与启动自检（db_health）调用
"""
import glob
import json
import logging
import os
import re
import shutil
import sqlite3
import zipfile
from datetime import datetime

from config import (CHROMA_PATH, DATA_DIR, DATABASE_URL, DB_PATH,
                    EXPORT_DIR, FRONTEND_DIR, UPLOAD_DIR)

logger = logging.getLogger(__name__)

BACKUP_DIR = os.path.join(DATA_DIR, "backups")
# 完整备份的 DB 临时快照放独立目录：不进备份列表、不占 MAX_BACKUPS 配额、不被自动恢复选中
SNAPSHOT_DIR = os.path.join(DATA_DIR, ".backup_tmp")
MAX_BACKUPS = 14
DB_PATTERN = "tutoring-*.db"
FULL_PATTERN = "tutoring-full-*.zip"


def _is_sqlite() -> bool:
    """当前数据库是否为 SQLite（非 SQLite 时跳过 sqlite3 备份，服务器切库后另实现）"""
    return DATABASE_URL.split(":", 1)[0].split("+", 1)[0].lower() == "sqlite"


def _ensure_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)


def _unique_path(path: str) -> str:
    """文件名撞秒时追加 -2/-3 后缀，避免覆盖同秒旧备份"""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{base}-{n}{ext}"):
        n += 1
    return f"{base}-{n}{ext}"


def _app_version() -> str:
    """从 frontend/index.html 读 APP_VERSION（与前端版本号保持同源）"""
    try:
        with open(os.path.join(FRONTEND_DIR, "index.html"), encoding="utf-8") as f:
            m = re.search(r"APP_VERSION\s*=\s*'(\d+)'", f.read())
            return m.group(1) if m else ""
    except Exception:
        return ""


def backup_database(full: bool = False) -> str:
    """执行一次备份；full=False 纯 DB 备份，full=True 完整 zip（DB+uploads+chroma+exports）。
    返回备份文件路径；失败返回 None（不抛异常，不阻塞启动）"""
    if not _is_sqlite():
        return None  # 非 SQLite（服务器切 PostgreSQL）时跳过，备份策略另行实现
    _ensure_dir()
    if not os.path.exists(DB_PATH):
        return None
    try:
        return _backup_full() if full else _backup_db_only()
    except Exception:
        logger.exception("备份失败")
        return None


def _backup_db_only() -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = _unique_path(os.path.join(BACKUP_DIR, f"tutoring-{ts}.db"))
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
            logger.exception("数据库备份失败")
            return None
    _prune()
    return dest


def _zip_tree(zf: zipfile.ZipFile, root: str, prefix: str):
    """把目录整树写入 zip（arcname 形如 uploads/xxx）。根目录存在才写"""
    if not os.path.isdir(root):
        return
    parent = os.path.dirname(root.rstrip("/\\"))
    for dirpath, dirnames, filenames in os.walk(root):
        # 跳过隐藏/缓存目录（ChromaDB 内部无锁文件需留，但 __pycache__ 等不必要）
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "__pycache__"]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, parent).replace("\\", "/")
            try:
                zf.write(full, rel)
            except OSError:
                continue  # 个别文件被占用/丢失不阻塞整体备份


def _backup_full() -> str:
    """完整备份 zip：先在线备份出 DB 一致快照，释放 Chroma 句柄后打包 uploads/chroma/exports"""
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = _unique_path(os.path.join(BACKUP_DIR, f"tutoring-full-{ts}.zip"))
    db_snapshot = os.path.join(SNAPSHOT_DIR, f"snapshot-{ts}.db")
    try:
        # 1) DB 在线快照到临时文件，保证 DB 一致性（不直接 copy 活跃 DB）
        try:
            src = sqlite3.connect(DB_PATH)
            dst = sqlite3.connect(db_snapshot)
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
        except Exception:
            shutil.copy2(DB_PATH, db_snapshot)  # 兜底

        # 2) 释放 ChromaDB 句柄（best-effort），避免拷到 WAL 半途状态
        try:
            from backend.services.kb_service import close_client
            close_client()
        except Exception:
            pass

        manifest = {
            "type": "full-backup",
            "app_version": _app_version(),
            "created_at": datetime.now().isoformat(),
            "schema_version": 1,
            "contains": ["tutoring.db", "uploads/", "chroma_data/", "exports/"],
        }
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(db_snapshot, "tutoring.db")
            _zip_tree(zf, UPLOAD_DIR, "uploads")
            _zip_tree(zf, CHROMA_PATH, "chroma_data")
            _zip_tree(zf, EXPORT_DIR, "exports")
            zf.writestr("MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        _prune()
        return dest
    except Exception:
        logger.exception("完整备份失败")
        try:
            if os.path.exists(dest):
                os.remove(dest)
        except OSError:
            pass
        return None
    finally:
        try:
            if os.path.exists(db_snapshot):
                os.remove(db_snapshot)
        except OSError:
            pass


def list_backups() -> list:
    """列出全部备份：[{filename, size, created_at, type}]，按修改时间倒序"""
    _ensure_dir()
    files = glob.glob(os.path.join(BACKUP_DIR, "*.db")) + glob.glob(os.path.join(BACKUP_DIR, "*.zip"))
    files = sorted(files, key=os.path.getmtime, reverse=True)
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
            "type": "full" if f.endswith(".zip") else "db",
        })
    return result


def _safe_backup_path(filename: str):
    """校验 filename 为 BACKUP_DIR 内合法备份文件名，返回绝对路径；非法返回 None。
    防路径遍历（.. / 绝对路径 / 子目录 / 非备份后缀）"""
    if not filename or not isinstance(filename, str):
        return None
    if filename != os.path.basename(filename):
        return None
    if not (filename.endswith(".db") or filename.endswith(".zip")):
        return None
    base_abs = os.path.abspath(BACKUP_DIR)
    path = os.path.abspath(os.path.join(BACKUP_DIR, filename))
    if os.path.commonpath([base_abs, path]) != base_abs:
        return None
    return path


def delete_backup(filename: str) -> bool:
    """删除指定备份；文件不存在/非法返回 False"""
    path = _safe_backup_path(filename)
    if not path or not os.path.exists(path):
        return False
    os.remove(path)
    return True


def restore_db_from_file(backup_path: str) -> bool:
    """用 sqlite3 online backup 从备份文件覆盖当前 DB，成功后刷新 SQLAlchemy 连接池。
    这是纯 DB 在线恢复的唯一实现（restore_database / db_health 共用）"""
    try:
        src = sqlite3.connect(backup_path, timeout=10)
        dst = sqlite3.connect(DB_PATH, timeout=10)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
    except Exception as e:
        logger.error("从备份 %s 恢复失败: %s", backup_path, e)
        return False
    try:
        from backend.models import engine
        engine.dispose()
    except Exception:
        pass
    return True


def restore_database(filename: str) -> dict:
    """从备份恢复（设置页一键恢复）。
    .db → 纯 DB 在线恢复（先反悔快照）；.zip → 完整恢复（migrate.apply_package）。
    返回 {restored, pre_snapshot, warnings}；校验失败抛 ValueError/RuntimeError"""
    path = _safe_backup_path(filename)
    if not path or not os.path.exists(path):
        raise ValueError("备份文件不存在")

    # 完整备份 zip → 走迁移包通用恢复（DB + uploads + chroma + exports）
    if filename.endswith(".zip"):
        from backend.utils.migrate import apply_package
        result = apply_package(path, pre_snapshot=True)
        result["restored"] = "full"  # 与 .db 分支返回形状统一
        return result

    # 纯 DB：先校验备份完整性（防手拷/截断的坏备份覆盖活库），再对当前库做反悔快照，再在线恢复
    from backend.utils.db_health import check_db_integrity
    res = check_db_integrity(path)
    if res["error"] is not None or res["quick_check"] != "ok":
        raise ValueError("备份文件损坏，无法恢复")
    pre = _backup_db_only()
    if not restore_db_from_file(path):
        raise RuntimeError("数据库恢复失败")
    # 刷新：老备份可能缺新列（补迁移）+ AI 配置内存缓存重置
    from backend.models import init_db
    init_db()
    from backend.ai.manager import ai_manager
    ai_manager.reload_config()
    return {
        "restored": "db",
        "pre_snapshot": os.path.basename(pre) if pre else "",
        "warnings": [],
    }


def _prune():
    """统一按修改时间合并 .db + .zip，保留最近 MAX_BACKUPS 份"""
    files = sorted(
        glob.glob(os.path.join(BACKUP_DIR, "*.db")) + glob.glob(os.path.join(BACKUP_DIR, "*.zip")),
        key=os.path.getmtime,
    )
    for f in files[:-MAX_BACKUPS]:
        try:
            os.remove(f)
        except OSError:
            pass
