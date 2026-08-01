"""
OpenAI Provider — 官方 API + Embedding
"""
from openai import OpenAI

from backend.ai.base import BaseLLMProvider


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
            timeout=60.0,
        )

    def chat(self, messages, **kwargs) -> str:
        resp = self._client.chat.completions.create(
            model=kwargs.get("model") or self.model_name,
            messages=messages,
            temperature=kwargs.get("temperature", self.temperature),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            stream=False,
        )
        return resp.choices[0].message.content or ""

    def chat_stream(self, messages, **kwargs):
        stream = self._client.chat.completions.create(
            model=kwargs.get("model") or self.model_name,
            messages=messages,
            temperature=kwargs.get("temperature", self.temperature),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            stream=True,
        )
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