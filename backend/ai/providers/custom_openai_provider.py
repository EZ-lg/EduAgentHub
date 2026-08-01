"""
自定义 OpenAI 兼容 Provider — 可接 Ollama / vLLM / LM Studio / 任意兼容服务
"""
from backend.ai.providers.openai_provider import OpenAIProvider


class CustomOpenAIProvider(OpenAIProvider):
    name = "custom_openai"
    label = "自定义兼容(OpenAI)"
    supports_embedding = True
    default_base_url = "http://localhost:11434/v1"   # Ollama 默认地址
    default_models = []
    default_embedding_models = []