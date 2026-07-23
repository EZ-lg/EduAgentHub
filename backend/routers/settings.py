"""
系统设置 API（P2 实现完整逻辑）
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.models import get_db
from backend.models.setting import Setting
from backend.utils.helpers import success_response, now_iso

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    """获取所有设置"""
    settings = db.query(Setting).all()
    result = {}
    for s in settings:
        result[s.key] = s.to_dict()
    return success_response(result)


@router.put("")
def update_settings(data: dict, db: Session = Depends(get_db)):
    """批量更新设置"""
    for key, value_json in data.items():
        setting = db.query(Setting).filter(Setting.key == key).first()
        if setting:
            setting.value_json = value_json if isinstance(value_json, str) else str(value_json)
            setting.updated_at = now_iso()
        else:
            setting = Setting(
                key=key,
                value_json=value_json if isinstance(value_json, str) else str(value_json),
            )
            db.add(setting)
    db.commit()
    return success_response({"updated": True})


@router.post("/test-llm")
def test_llm(data: dict = None):
    """测试 LLM 连接（P2 实现）"""
    return success_response({"info": "LLM 测试功能将在 P2 实现"})


@router.post("/test-embed")
def test_embed(data: dict = None):
    """测试 Embedding 连接（P2 实现）"""
    return success_response({"info": "Embedding 测试功能将在 P2 实现"})
