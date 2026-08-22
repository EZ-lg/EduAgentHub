"""
换机迁移与完整恢复 — 数据包的校验 / 安全解压 / 应用

完整备份 zip（tutoring-full-*.zip）与导入数据包共用 apply_package 作为恢复核心：
校验 → 反悔快照 → 释放连接 → staged 解压 → DB 校验 → 替换现场 → KB 路径归一化 → 重初始化。

安全要点：
- 防 zip 穿越：逐成员校验，白名单前缀 + normpath 必须在解压根内
- 防 zip-bomb：累计解压大小上限 MAX_PKG_SIZE
- 导入前自动反悔快照；staged 成功后才动现场；全程 try/finally 清理
- 换机后 knowledge_docs.file_path 存的是旧机绝对路径，导入后重写指向新 UPLOAD_DIR
"""
import logging
import os
import shutil
import tempfile
import zipfile

from config import CHROMA_PATH, EXPORT_DIR, UPLOAD_DIR

logger = logging.getLogger(__name__)

# 解压总量上限（防 zip-bomb）；成员数上限
MAX_PKG_SIZE = 2 * 1024 * 1024 * 1024  # 2GB（含 uploads/chroma 的完整包通常远小于此）
MAX_PKG_FILES = 200_000

ALLOWED_PREFIXES = ("tutoring.db", "uploads", "chroma_data", "exports", "MANIFEST.json")


def _member_allowed(name: str) -> bool:
    """成员名白名单：根级 tutoring.db / MANIFEST.json 或 uploads|chroma_data|exports 下任意"""
    name = name.replace("\\", "/").lstrip("/")
    if name == "tutoring.db" or name == "MANIFEST.json":
        return True
    for prefix in ("uploads", "chroma_data", "exports"):
        if name == prefix or name.startswith(prefix + "/"):
            return True
    return False


def validate_package(zip_path: str) -> dict:
    """校验数据包结构与内容。返回 {ok, error, has_db, db_valid, total_size, files}"""
    result = {"ok": False, "error": "", "has_db": False, "db_valid": False,
              "total_size": 0, "files": []}
    if not os.path.exists(zip_path):
        result["error"] = "数据包不存在"
        return result
    try:
        with zipfile.ZipFile(zip_path) as zf:
            total = 0
            for m in zf.infolist():
                name = m.filename.replace("\\", "/").lstrip("/")
                if not _member_allowed(name):
                    result["error"] = f"数据包包含非法条目: {name}"
                    return result
                if name == "tutoring.db" and not m.is_dir():
                    result["has_db"] = True
                total += m.file_size
                result["files"].append(name)
            result["total_size"] = total
            if len(result["files"]) > MAX_PKG_FILES:
                result["error"] = "数据包文件过多"
                return result
            if total > MAX_PKG_SIZE:
                result["error"] = "数据包过大，超过解压上限"
                return result
            if not result["has_db"]:
                result["error"] = "数据包缺少 tutoring.db"
                return result
            # 抽取出 tutoring.db 做完整性校验（quick_check；缺表由 init_db 迁移补齐，不阻塞）
            with tempfile.TemporaryDirectory(prefix="edu_validate_") as td:
                db_tmp = os.path.join(td, "tutoring.db")
                with zf.open("tutoring.db") as src, open(db_tmp, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                from backend.utils.db_health import check_db_integrity
                res = check_db_integrity(db_tmp)
                if res["quick_check"] != "ok":
                    result["error"] = "数据包内数据库校验失败（文件损坏）"
                    return result
                result["db_valid"] = True
    except zipfile.BadZipFile:
        result["error"] = "不是有效的 zip 数据包"
        return result
    except (OSError, ValueError) as e:
        result["error"] = f"数据包读取失败: {e}"
        return result
    result["ok"] = True
    return result


def _extract_safe(zip_path: str, dest_dir: str):
    """防穿越 + 防 zip-bomb 解压到 dest_dir（dest_dir 必须先存在）"""
    total = 0
    base_abs = os.path.abspath(dest_dir)
    with zipfile.ZipFile(zip_path) as zf:
        for m in zf.infolist():
            name = m.filename.replace("\\", "/").lstrip("/")
            if not _member_allowed(name):
                raise ValueError(f"数据包包含非法条目: {name}")
            if name.startswith("/") or ".." in name.split("/"):
                raise ValueError(f"非法路径: {m.filename}")
            norm = os.path.normpath(name)
            if os.path.isabs(norm):
                raise ValueError(f"非法路径: {m.filename}")
            target = os.path.abspath(os.path.join(dest_dir, norm))
            if os.path.commonpath([base_abs, target]) != base_abs:
                raise ValueError(f"非法路径: {m.filename}")
            total += m.file_size
            if total > MAX_PKG_SIZE:
                raise ValueError("数据包过大，超过解压上限")
            if m.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(m) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)


def _replace_dir(staged: str, target: str, label: str, warnings: list, chroma: bool = False):
    """原子替换 target 目录（不丢当前数据）：
    先把现有 target 移到 .bak 保底 → 从 staged 拷贝新内容 → 成功删 .bak；
    任一步失败回滚（.bak 移回）。磁盘满/文件被占用时原数据仍在 .bak，绝不先删后拷。"""
    os.makedirs(target, exist_ok=True)
    staged_exists = os.path.isdir(staged)
    bak = ""
    try:
        # 1) 现有 target 移走保底
        if os.path.exists(target) and os.listdir(target):
            bak = target + ".bak"
            if os.path.exists(bak):
                shutil.rmtree(bak, ignore_errors=True)
            shutil.move(target, bak)
        # 2) staged → 新 target
        if staged_exists:
            shutil.copytree(staged, target)
        else:
            os.makedirs(target, exist_ok=True)
        # 3) 成功：清理 .bak
        if bak:
            shutil.rmtree(bak, ignore_errors=True)
    except OSError as e:
        # 失败回滚：删不完整 target，把 .bak 移回恢复原数据
        if os.path.exists(target):
            shutil.rmtree(target, ignore_errors=True)
        if bak and os.path.exists(bak):
            try:
                shutil.move(bak, target)
            except OSError:
                warnings.append(f"{label} 回滚失败，原数据已保留在 {os.path.basename(bak)}，请手工处理")
        _chroma_fallback(chroma, label, e, warnings)


def _chroma_fallback(chroma: bool, label: str, e: OSError, warnings: list):
    if chroma:
        warnings.append(f"chroma_data 被占用未能替换（{e}），请重启程序后重建知识库")
        _mark_kb_pending()
    else:
        warnings.append(f"替换 {label} 部分失败：{e}")


def _mark_kb_pending():
    """chroma_data 替换失败时，把知识库文档标记为待重建（UI 已有 index_status 字段）"""
    try:
        from backend.models import SessionLocal
        from backend.models.knowledge_doc import KnowledgeDoc
        db = SessionLocal()
        try:
            for doc in db.query(KnowledgeDoc).all():
                doc.index_status = "pending"
            db.commit()
        finally:
            db.close()
    except Exception:
        logger.exception("标记知识库 pending 失败")


def _normalize_kb_paths() -> int:
    """换机后 knowledge_docs.file_path 存的是旧机绝对路径，重写指向新 UPLOAD_DIR。返回修正数"""
    from backend.models import SessionLocal
    from backend.models.knowledge_doc import KnowledgeDoc
    db = SessionLocal()
    try:
        changed = 0
        for doc in db.query(KnowledgeDoc).all():
            if not doc.file_path:
                continue
            base = os.path.basename(doc.file_path)
            if not base:
                continue
            candidate = os.path.join(UPLOAD_DIR, base)
            if doc.file_path != candidate and os.path.exists(candidate):
                doc.file_path = candidate
                changed += 1
        if changed:
            db.commit()
        return changed
    finally:
        db.close()


def apply_package(zip_path: str, pre_snapshot: bool = True) -> dict:
    """应用完整数据包（恢复 .zip / 导入数据包共用）。
    返回 {applied, pre_snapshot, warnings}；校验失败抛 ValueError，应用失败抛 RuntimeError"""
    validation = validate_package(zip_path)
    if not validation["ok"]:
        raise ValueError(validation["error"])

    warnings = []
    pre = ""
    staging = tempfile.mkdtemp(prefix="edu_import_")
    try:
        # 先把源包复制进 staging 保护起来，再生成反悔快照：
        # 若备份清理（_prune）删掉了"被恢复的最旧源包"，后续解压仍可用 staging 副本，不中断恢复
        input_zip = os.path.join(staging, "input.zip")
        shutil.copy2(zip_path, input_zip)

        if pre_snapshot:
            from backend.utils.backup import backup_database
            pre = backup_database(full=True)
            if not pre:
                warnings.append("当前数据反悔快照生成失败，请谨慎继续")

        _extract_safe(input_zip, staging)
        staged_db = os.path.join(staging, "tutoring.db")
        if not os.path.exists(staged_db):
            raise ValueError("数据包缺少 tutoring.db")

        # 释放当前连接 / ChromaDB 句柄，避免 Windows 覆盖被占用
        from backend.models import engine
        engine.dispose()
        try:
            from backend.services.kb_service import close_client
            close_client()
        except Exception:
            pass

        # 1) 数据库：online backup 覆盖（一致性），随后补迁移 + 刷新
        from backend.utils.backup import restore_db_from_file
        if not restore_db_from_file(staged_db):
            raise RuntimeError("数据包数据库应用失败")
        from backend.models import init_db
        init_db()

        # 2) uploads / exports / chroma_data 整体替换
        _replace_dir(os.path.join(staging, "uploads"), UPLOAD_DIR, "uploads", warnings)
        _replace_dir(os.path.join(staging, "exports"), EXPORT_DIR, "exports", warnings)
        _replace_dir(os.path.join(staging, "chroma_data"), CHROMA_PATH, "chroma_data", warnings, chroma=True)

        # 3) 跨机 KB 路径归一化
        changed = _normalize_kb_paths()
        if changed:
            warnings.append(f"已修正 {changed} 个知识库文档的存储路径")

        # 4) AI 配置内存缓存重置（settings 表可能被整体替换）
        from backend.ai.manager import ai_manager
        ai_manager.reload_config()

        return {
            "applied": True,
            "pre_snapshot": os.path.basename(pre) if pre else "",
            "warnings": warnings,
        }
    finally:
        shutil.rmtree(staging, ignore_errors=True)
