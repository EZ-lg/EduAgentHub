"""
BaseLLMProvider — 所有 LLM/Embedding Provider 的抽象基类

新 Provider 只需实现 chat() / chat_stream() / embed() 中自身支持的能力，
健康检查和元信息暴露由基类统一处理。
"""
import time
from typing import List, Dict, Generator, Optional


class BaseLLMProvider:
    """所有大模型 Provider 的抽象基类"""

    # ---- 类级元信息（子类覆盖） ----
    name: str = "base"                          # provider 标识，与 settings 中 provider 字段一致
    label: str = "Base"                         # 显示名称（设置页下拉）
    supports_chat: bool = True
    supports_embedding: bool = False
    default_base_url: str = ""
    default_models: List[str] = []              # 聊天模型候选
    default_embedding_models: List[str] = []    # 向量模型候选

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.api_key = self.config.get("api_key", "")
        self.base_url = self.config.get("base_url", "") or self.default_base_url
        self.model_name = self.config.get("model_name", "")
        self.temperature = float(self.config.get("temperature", 0.7))
        self.max_tokens = int(self.config.get("max_tokens", 4096))
        # 向量模型名独立配置（与聊天模型分开）
        self.embedding_model = self.config.get(
            "embedding_model", ""
        ) or (self.default_embedding_models[0] if self.default_embedding_models else "")

    # ==================== 子类必须实现 ====================
    def chat(self, messages: List[dict], **kwargs) -> str:
        """非流式对话，返回完整文本"""
        raise NotImplementedError(f"{self.label} 未实现 chat()")

    def chat_stream(self, messages: List[dict], **kwargs) -> Generator[str, None, None]:
        """流式对话，逐段 yield 文本"""
        raise NotImplementedError(f"{self.label} 未实现 chat_stream()")

    def embed(self, texts: List[str]) -> List[List[float]]:
        """文本向量化，返回每个文本的向量"""
        raise NotImplementedError(f"{self.label} 未实现 embed()")

    # ==================== 健康检查 ====================
    def check_chat(self) -> dict:
        """测试聊天能力"""
        start = time.time()
        try:
            resp = self.chat(
                [{"role": "user", "content": "你好，请只回复两个字：正常"}],
                max_tokens=20,
            )
            latency_ms = int((time.time() - start) * 1000)
            if not resp or not resp.strip():
                return {"ok": False, "message": "模型返回为空", "latency_ms": latency_ms}
            return {
                "ok": True,
                "message": f"连接成功，模型回复：{resp.strip()[:20]}",
                "latency_ms": latency_ms,
            }
        except Exception as e:
            latency_ms = int((time.time() - start) * 1000)
            return {"ok": False, "message": str(e), "latency_ms": latency_ms}

    def check_embed(self) -> dict:
        """测试向量化能力"""
        start = time.time()
        try:
            vecs = self.embed(["连接测试"])
            latency_ms = int((time.time() - start) * 1000)
            dim = len(vecs[0]) if vecs and len(vecs) > 0 else 0
            if not vecs or dim == 0:
                return {"ok": False, "message": "Embedding 返回为空", "latency_ms": latency_ms}
            return {
                "ok": True,
                "message": f"连接成功，向量维度 {dim}",
                "latency_ms": latency_ms,
            }
        except Exception as e:
            latency_ms = int((time.time() - start) * 1000)
            return {"ok": False, "message": str(e), "latency_ms": latency_ms}

    def health_check(self, mode: str = "chat") -> dict:
        """统一健康检查入口。mode: chat | embed"""
        if mode == "embed":
            if not self.supports_embedding:
                return {"ok": False, "message": f"{self.label} 不支持 Embedding", "latency_ms": 0}
            return self.check_embed()
        return self.check_chat()

    # ==================== 元信息（供前端设置页） ====================
    @classmethod
    def to_meta(cls) -> dict:
        return {
            "name": cls.name,
            "label": cls.label,
            "supports_chat": cls.supports_chat,
            "supports_embedding": cls.supports_embedding,
            "default_base_url": cls.default_base_url,
            "default_models": cls.default_models,
            "default_embedding_models": cls.default_embedding_models,
        }