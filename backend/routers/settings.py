"""
系统设置 API（P2 实现完整逻辑）

- GET/PUT /api/settings          读取/批量更新设置（value_json 存 JSON 字符串）
- GET  /api/settings/providers   获取 Provider 元信息（前端设置页渲染下拉框）
- POST /api/settings/test-llm    测试 LLM 连接
- POST /api/settings/test-embed  测试 Embedding 连接
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.ai.factory import create_provider, get_provider_meta
from backend.ai.manager import ai_manager, LLM_CONFIG_KEY, EMBEDDING_CONFIG_KEY
from backend.models import get_db
from backend.models.setting import Setting
from backend.utils.helpers import success_response, now_iso

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _parse_value(value) -> dict:
    """将存储的 value_json 解析为 JSON 对象"""
    if value is None:
        return {}
    if isinstance(value, (dict, list)):
        return value
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


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
