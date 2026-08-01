"""
通义千问 Provider — DashScope OpenAI 兼容模式，Chat + Embedding
"""
from backend.ai.providers.openai_provider import OpenAIProvider


class QwenProvider(OpenAIProvider):
    name = "qwen"
    label = "通义千问"
    supports_embedding = True
    default_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    default_models = ["qwen-max", "qwen-plus", "qwen-turbo", "qwen-long"]
    default_embedding_models = ["text-embedding-v4", "text-embedding-v3", "text-embedding-v2"]