"""
OpenAI Provider — 官方 API + Embedding
"""
from openai import OpenAI

from backend.ai.base import BaseLLMProvider

# OpenAI 推理模型（o 系列 / gpt-5）：max_tokens 需改用 max_completion_tokens，不支持 temperature
OPENAI_REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5")
# DeepSeek 推理模型：仍用 max_tokens，但同样不支持 temperature（部分兼容网关会 400）
DEEPSEEK_REASONING_MODELS = ("deepseek-reasoner",)


def _is_openai_reasoning(model: str) -> bool:
    return (model or "").lower().startswith(OPENAI_REASONING_PREFIXES)


def _is_reasoning_model(model: str) -> bool:
    m = (model or "").lower()
    return m.startswith(OPENAI_REASONING_PREFIXES) or m.startswith(DEEPSEEK_REASONING_MODELS)


class OpenAIProvider(BaseLLMProvider):
    name = "openai"
    label = "OpenAI"
    supports_embedding = True
    default_base_url = "https://api.openai.com/v1"
    default_models = ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "o4-mini"]
    default_embedding_models = ["text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"]

    def __init__(self, config: dict = None):
        super().__init__(config)
        self._client = OpenAI(
            api_key=self.api_key or "EMPTY",
            base_url=self.base_url or self.default_base_url,
            timeout=120.0,  # 长报告/推理模型常超 60s，放宽到 120s
        )

    def _build_params(self, messages, kwargs, stream=False) -> dict:
        """按模型类型组装参数：推理模型省略 temperature；OpenAI o 系列用 max_completion_tokens"""
        model = kwargs.get("model") or self.model_name
        params = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        if _is_openai_reasoning(model):
            # o 系列 / gpt-5：max_tokens → max_completion_tokens
            params["max_completion_tokens"] = kwargs.get("max_tokens", self.max_tokens)
        else:
            # 普通模型与 deepseek-reasoner 仍用 max_tokens
            params["max_tokens"] = kwargs.get("max_tokens", self.max_tokens)
        if not _is_reasoning_model(model):
            # deepseek-reasoner / o 系列不支持 temperature
            params["temperature"] = kwargs.get("temperature", self.temperature)
        return params

    def chat(self, messages, **kwargs) -> str:
        resp = self._client.chat.completions.create(**self._build_params(messages, kwargs))
        return resp.choices[0].message.content or ""

    def chat_stream(self, messages, **kwargs):
        stream = self._client.chat.completions.create(**self._build_params(messages, kwargs, stream=True))
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta

    def embed(self, texts):
        if not isinstance(texts, list):
            texts = [texts]
        model = self.embedding_model or (self.default_embedding_models[0] if self.default_embedding_models else "")
        resp = self._client.embeddings.create(model=model, input=texts)
        return [item.embedding for item in resp.data]