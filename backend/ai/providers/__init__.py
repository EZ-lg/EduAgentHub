"""
Provider 注册表 — 新增 Provider 只需在此导入并加入 factory.PROVIDER_CLASSES
"""
from backend.ai.providers.openai_provider import OpenAIProvider
from backend.ai.providers.deepseek_provider import DeepSeekProvider
from backend.ai.providers.claude_provider import ClaudeProvider
from backend.ai.providers.qwen_provider import QwenProvider
from backend.ai.providers.custom_openai_provider import CustomOpenAIProvider

__all__ = [
    "OpenAIProvider",
    "DeepSeekProvider",
    "ClaudeProvider",
    "QwenProvider",
    "CustomOpenAIProvider",
]
