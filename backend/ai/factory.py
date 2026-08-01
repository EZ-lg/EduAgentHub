"""
AI Provider 工厂 — 根据 provider 名称创建对应实例

新增 Provider 的步骤：
1. 在 backend/ai/providers/ 下新建一个类（继承 BaseLLMProvider）
2. 在 providers/__init__.py 中导入
3. 在本文件的 PROVIDER_CLASSES 中登记即可
"""
from typing import Dict, Type

from backend.ai.base import BaseLLMProvider
from backend.ai.providers import (
    OpenAIProvider,
    DeepSeekProvider,
    ClaudeProvider,
    QwenProvider,
    CustomOpenAIProvider,
)

# provider 名称 → 类（名称与 settings 配置中的 provider 字段对应）
PROVIDER_CLASSES: Dict[str, Type[BaseLLMProvider]] = {
    "openai": OpenAIProvider,
    "deepseek": DeepSeekProvider,
    "claude": ClaudeProvider,
    "qwen": QwenProvider,
    "custom_openai": CustomOpenAIProvider,
}


def get_provider_class(name: str):
    """根据名称获取 Provider 类，未找到返回 None"""
    if not name:
        return None
    return PROVIDER_CLASSES.get(str(name).strip().lower())


def create_provider(config: dict) -> BaseLLMProvider:
    """根据配置 dict 创建 Provider 实例"""
    if not config:
        raise ValueError("AI 配置为空")
    cls = get_provider_class(config.get("provider", ""))
    if not cls:
        raise ValueError(f"未知的 Provider: {config.get('provider')}")
    return cls(config)


def get_provider_meta() -> dict:
    """返回所有 Provider 的元信息，供前端设置页渲染下拉框"""
    return {name: cls.to_meta() for name, cls in PROVIDER_CLASSES.items()}