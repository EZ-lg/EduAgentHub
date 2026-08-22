"""
AIManager 单例 — 负责 LLM / Embedding Provider 的创建与缓存

- 从 settings 表读取 llm_config / embedding_config（key-value，value_json 为 JSON 字符串）
- 根据 provider 字段创建对应 Provider 实例
- 配置变化时调用 reload_config() 清除缓存
- 全局通过 ai_manager 单例使用
"""
import json
import logging
import threading
from typing import Optional

from backend.ai.base import BaseLLMProvider
from backend.ai.factory import create_provider
from backend.models import SessionLocal
from backend.models.setting import Setting

logger = logging.getLogger(__name__)

LLM_CONFIG_KEY = "llm_config"
EMBEDDING_CONFIG_KEY = "embedding_config"


class AIManager:
    _instance: Optional["AIManager"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._llm: Optional[BaseLLMProvider] = None
        self._embedding: Optional[BaseLLMProvider] = None
        self._llm_sig: Optional[str] = None
        self._embedding_sig: Optional[str] = None
        self._initialized = True

    # ---------------- 配置读取 ----------------
    def _read_config(self, key: str) -> Optional[dict]:
        """从 settings 表读取并解析 JSON 配置"""
        db = SessionLocal()
        try:
            setting = db.query(Setting).filter(Setting.key == key).first()
            if not setting or not setting.value_json:
                return None
            try:
                data = json.loads(setting.value_json)
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
        finally:
            db.close()

    @staticmethod
    def _signature(config: dict) -> str:
        """配置签名，用于检测配置是否变化"""
        if not config:
            return ""
        return json.dumps(config, sort_keys=True, ensure_ascii=False)

    # ---------------- Provider 获取（带缓存） ----------------
    def _get(self, key: str, slot: str) -> Optional[BaseLLMProvider]:
        config = self._read_config(key)
        if not config or not config.get("provider"):
            return None
        sig = self._signature(config)
        cached = getattr(self, f"_{slot}")
        if cached is not None and getattr(self, f"_{slot}_sig") == sig:
            return cached
        # 配置变化或首次创建
        try:
            provider = create_provider(config)
        except Exception:
            # 不要静默吞掉：非法配置（如 temperature 填了非数字）会在此抛错，
            # 若吞掉会让 is_configured()=True 但 get_llm()=None，调用方误报"AI 未配置"
            logger.exception("Provider 创建失败（配置可能非法）：provider=%s", config.get("provider"))
            return None
        setattr(self, f"_{slot}", provider)
        setattr(self, f"_{slot}_sig", sig)
        return provider

    def get_llm(self) -> Optional[BaseLLMProvider]:
        """获取 LLM Provider（未配置返回 None）"""
        return self._get(LLM_CONFIG_KEY, "llm")

    def get_embedding(self) -> Optional[BaseLLMProvider]:
        """获取 Embedding Provider（未配置返回 None）"""
        return self._get(EMBEDDING_CONFIG_KEY, "embedding")

    # ---------------- 状态判断 ----------------
    def is_configured(self, kind: str = "llm") -> bool:
        """是否已配置（provider 已选即视为配置过，api_key 可为空以支持本地模型）"""
        key = LLM_CONFIG_KEY if kind == "llm" else EMBEDDING_CONFIG_KEY
        cfg = self._read_config(key)
        return bool(cfg and cfg.get("provider"))

    def reload_config(self):
        """清除缓存，下次获取时重新读取配置（切换模型后调用）"""
        self._llm = None
        self._embedding = None
        self._llm_sig = None
        self._embedding_sig = None


# 全局单例
ai_manager = AIManager()