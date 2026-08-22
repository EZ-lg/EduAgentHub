"""
Claude Provider — Anthropic 官方 API，仅 Chat（分析深度最优）
"""
from typing import List

from anthropic import Anthropic

from backend.ai.base import BaseLLMProvider


class ClaudeProvider(BaseLLMProvider):
    name = "claude"
    label = "Claude"
    supports_embedding = False
    default_base_url = "https://api.anthropic.com"
    default_models = ["claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5-20251001"]
    default_embedding_models = []

    def __init__(self, config: dict = None):
        super().__init__(config)
        kwargs = {"api_key": self.api_key or "EMPTY", "timeout": 120.0}  # 长报告常超 60s
        if self.base_url and self.base_url != self.default_base_url:
            kwargs["base_url"] = self.base_url
        self._client = Anthropic(**kwargs)

    def _to_anthropic_messages(self, messages: List[dict]):
        """转换为 Anthropic 格式：system 单独提取，连续同角色消息合并（Anthropic 要求交替）"""
        system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
        user_msgs = [m for m in messages if m.get("role") != "system"]
        merged = []
        for m in user_msgs:
            role = "user" if m.get("role") == "user" else "assistant"
            content = m.get("content", "")
            if merged and merged[-1]["role"] == role:
                merged[-1]["content"] += "\n" + content
            else:
                merged.append({"role": role, "content": content})
        return system, merged

    def chat(self, messages, **kwargs) -> str:
        system, msgs = self._to_anthropic_messages(messages)
        resp = self._client.messages.create(
            model=kwargs.get("model") or self.model_name,
            system=system or None,
            messages=msgs,
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            temperature=kwargs.get("temperature", self.temperature),
        )
        return "".join(block.text for block in resp.content if block.type == "text")

    def chat_stream(self, messages, **kwargs):
        system, msgs = self._to_anthropic_messages(messages)
        with self._client.messages.stream(
            model=kwargs.get("model") or self.model_name,
            system=system or None,
            messages=msgs,
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            temperature=kwargs.get("temperature", self.temperature),
        ) as stream:
            for text in stream.text_stream:
                yield text
