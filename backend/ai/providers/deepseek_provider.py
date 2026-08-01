"""
DeepSeek Provider — OpenAI 兼容协议，仅 Chat（性价比之选）
"""
from backend.ai.providers.openai_provider import OpenAIProvider


class DeepSeekProvider(OpenAIProvider):
    name = "deepseek"
    label = "DeepSeek"
    supports_embedding = False
    default_base_url = "https://api.deepseek.com/v1"
    default_models = ["deepseek-chat", "deepseek-reasoner"]
    default_embedding_models = []

    def embed(self, texts):
        raise NotImplementedError("DeepSeek 不提供 Embedding 服务，请改用 OpenAI / 通义千问 / 自定义兼容")