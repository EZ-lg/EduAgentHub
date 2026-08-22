"""
系统设置 API（P2 实现完整逻辑）

- GET/PUT /api/settings          读取/批量更新设置（value_json 存 JSON 字符串）
- GET  /api/settings/providers   获取 Provider 元信息（前端设置页渲染下拉框）
- POST /api/settings/test-llm    测试 LLM 连接
- POST /api/settings/test-embed  测试 Embedding 连接
"""
import json
import logging
import os
import tempfile
import time
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.ai.factory import create_provider, get_provider_meta
from backend.ai.manager import ai_manager, LLM_CONFIG_KEY, EMBEDDING_CONFIG_KEY
from backend.models import get_db
from backend.models.setting import Setting
from backend.utils.backup import (
    _safe_backup_path, backup_database, delete_backup, list_backups, restore_database,
)
from backend.utils.helpers import success_response, now_iso

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _parse_value(value):
    """将存储的 value_json 解析为 JSON 对象"""
    if value is None:
        return {}
    if isinstance(value, (dict, list)):
        return value
    try:
        data = json.loads(value)
        # 兼容列表设置（如 class_periods），此前列表会被降级成 {}
        return data if isinstance(data, (dict, list)) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _mask_api_key(key: str) -> str:
    """API key 掩码显示：前 4 位 + **** + 后 4 位（短 key 全掩）"""
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}****{key[-4:]}"


def _sanitize_config(config) -> dict:
    """GET 返回前对 LLM/Embedding 配置的 api_key 掩码，避免网络部署下明文泄露"""
    if not isinstance(config, dict):
        return config
    out = dict(config)
    if out.get("api_key"):
        out["api_key"] = _mask_api_key(str(out["api_key"]))
    return out


def _read_saved(db: Session, key: str) -> Optional[dict]:
    """读取已保存的某个设置项（解析为 dict）"""
    setting = db.query(Setting).filter(Setting.key == key).first()
    if not setting:
        return None
    return _parse_value(setting.value_json)


def _run_test(config: Optional[dict], mode: str, kind: str) -> dict:
    """创建 Provider 并执行健康检查"""
    if not config or not config.get("provider"):
        return success_response({"ok": False, "message": f"请先填写{kind}配置", "latency_ms": 0})
    try:
        provider = create_provider(config)
        result = provider.health_check(mode=mode)
        return success_response(result)
    except Exception as e:
        return success_response({"ok": False, "message": str(e), "latency_ms": 0})


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    """获取所有设置（value_json 解析为 JSON 对象）"""
    settings = db.query(Setting).all()
    result = {}
    for s in settings:
        if s.key in (LLM_CONFIG_KEY, EMBEDDING_CONFIG_KEY):
            # 敏感配置掩码 api_key（前端测试连接走 /test-llm 等接口，无需明文）
            result[s.key] = _sanitize_config(_parse_value(s.value_json))
        else:
            result[s.key] = _parse_value(s.value_json)
    return success_response(result)


@router.get("/providers")
def get_providers():
    """获取所有 Provider 元信息（名称、是否支持 Embedding、默认地址、模型候选等）"""
    return success_response({"providers": get_provider_meta()})


@router.put("")
def update_settings(data: dict, db: Session = Depends(get_db)):
    """批量更新设置。data 形如 {key: value}，value 为 dict/list 时自动转 JSON 存储"""
    keys = list(data.keys())
    for key, value in data.items():
        # 前端把掩码后的 api_key（含 ****）原样回传时，保留数据库里的真实 key，避免掩码覆盖
        if key in (LLM_CONFIG_KEY, EMBEDDING_CONFIG_KEY) and isinstance(value, dict) \
                and isinstance(value.get("api_key"), str) and "****" in value["api_key"]:
            existing = db.query(Setting).filter(Setting.key == key).first()
            if existing and existing.value_json:
                try:
                    old = json.loads(existing.value_json)
                    if isinstance(old, dict) and old.get("api_key"):
                        value = dict(value)
                        value["api_key"] = old["api_key"]
                except (json.JSONDecodeError, TypeError):
                    pass
        value_str = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        setting = db.query(Setting).filter(Setting.key == key).first()
        if setting:
            setting.value_json = value_str
            setting.updated_at = now_iso()
        else:
            db.add(Setting(key=key, value_json=value_str, updated_at=now_iso()))
    db.commit()
    # AI 配置变更后重载单例缓存
    if LLM_CONFIG_KEY in keys or EMBEDDING_CONFIG_KEY in keys:
        ai_manager.reload_config()
    return success_response({"updated": True})


@router.post("/test-llm")
def test_llm(data: dict = None, db: Session = Depends(get_db)):
    """测试 LLM 连接。body 传配置则用传入配置测试，否则用已保存配置"""
    config = data if (data and data.get("provider")) else _read_saved(db, LLM_CONFIG_KEY)
    return _run_test(config, mode="chat", kind="LLM")


@router.post("/test-embed")
def test_embed(data: dict = None, db: Session = Depends(get_db)):
    """测试 Embedding 连接。同上"""
    config = data if (data and data.get("provider")) else _read_saved(db, EMBEDDING_CONFIG_KEY)
    return _run_test(config, mode="embed", kind="Embedding")


@router.post("/backup")
def backup_now(full: bool = Query(False)):
    """立即备份数据库（?full=true 完整备份，含 uploads/chroma/exports）"""
    path = backup_database(full=full)
    if not path:
        raise HTTPException(status_code=500, detail="备份失败，请检查 data 目录权限")
    return success_response({
        "path": path,
        "size": os.path.getsize(path) if os.path.exists(path) else 0,
        "type": "full" if full else "db",
    })


@router.get("/backups")
def backups_list():
    """列出全部备份（数据管理）"""
    return success_response(list_backups())


# ---------------------------------------------------------------- P0 数据可靠性

@router.get("/health")
def health():
    """系统健康状态：DB 探活（轻量，不跑全库 quick_check 避免大库阻塞）+ 最近自检/修复记录 + 最近备份统计"""
    from backend.utils.db_health import HEALTH, check_db_integrity
    db = check_db_integrity(deep=False)
    backups = list_backups()
    last = backups[0] if backups else None
    return success_response({
        "healthy": db["quick_check"] == "ok" and db["tables_ok"],
        "db_ok": db["quick_check"] == "ok",
        "quick_check": db["quick_check"],
        "tables_ok": db["tables_ok"],
        "db_size": db["size"],
        "db_exists": db["exists"],
        "error": db["error"],
        "status": HEALTH.get("status"),
        "last_check": HEALTH.get("checked_at"),
        "last_repair": HEALTH.get("last_repair"),
        "last_repair_message": HEALTH.get("last_repair_message"),
        "last_backup": last["filename"] if last else None,
        "last_backup_at": last["created_at"] if last else None,
        "backup_count": len(backups),
    })


@router.post("/backups/restore")
def restore_backup(data: dict = None):
    """从备份一键恢复（.db 在线恢复 / .zip 完整恢复）。危险操作，前端需确认弹窗"""
    filename = (data or {}).get("filename", "")
    try:
        result = restore_database(filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    logger.info("已从备份 %s 恢复: %s", filename, result)
    return success_response(result)


@router.delete("/backups/{filename}")
def delete_backup_ep(filename: str):
    """删除单个备份"""
    if not delete_backup(filename):
        raise HTTPException(status_code=404, detail="备份文件不存在或文件名非法")
    return success_response({"deleted": True})


@router.get("/backups/{filename}/download")
def download_backup(filename: str):
    """下载备份文件（本地导出 / 存 U 盘）"""
    path = _safe_backup_path(filename)
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="备份文件不存在")
    return FileResponse(path, filename=filename, media_type="application/octet-stream")


@router.post("/migrate/export")
def migrate_export():
    """导出完整数据包（DB + uploads + chroma + exports），供换机迁移"""
    path = backup_database(full=True)
    if not path:
        raise HTTPException(status_code=500, detail="导出失败，请检查 data 目录权限")
    return success_response({
        "filename": os.path.basename(path),
        "size": os.path.getsize(path) if os.path.exists(path) else 0,
    })


@router.post("/migrate/import")
async def migrate_import(file: UploadFile = File(...)):
    """导入数据包（zip），覆盖当前数据。导入前自动生成反悔快照"""
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="请上传 .zip 数据包")
    from backend.utils.migrate import MAX_PKG_SIZE, apply_package
    tmp_path = os.path.join(tempfile.gettempdir(), f"edu_import_{int(time.time())}.zip")
    try:
        # 流式写入临时文件 + 大小上限：避免超大包整读内存导致 OOM 崩溃
        size = 0
        with open(tmp_path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_PKG_SIZE:
                    raise HTTPException(status_code=400, detail="数据包过大（超过解压上限）")
                out.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="空数据包")
        try:
            result = apply_package(tmp_path, pre_snapshot=True)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e))
        logger.info("导入数据包成功: %s", result)
        return success_response(result)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
