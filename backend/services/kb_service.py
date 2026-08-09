"""
知识库核心服务 — 切片 + Embedding + ChromaDB 入库/检索

设计要点：
- ChromaDB 嵌入式 PersistentClient，数据目录 config.CHROMA_PATH，无需独立服务
- 每个知识文档切分为多个 chunk，元数据含 doc_id / doc_title / category / chunk_index
- Embedding 统一走 AIManager 的 embedding Provider（与设置页配置联动）
- 集合 metadata 记录 embedding_model：切换模型后维度可能变化，检测到不一致
  抛 409 提示先重建知识库，避免 ChromaDB 维度报错造成困惑
- 检索按 active 文档过滤：查询前先取 DB 里 status=active 的 doc_id 集合，
  ChromaDB where 过滤，保证与启用/禁用开关永远一致
"""
import threading
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

import chromadb
from chromadb import PersistentClient

from backend.ai.manager import ai_manager
from backend.ai.prompts.prompt_loader import render_prompt
from backend.models.knowledge_doc import KnowledgeDoc
from backend.services import document_parser
from config import CHROMA_PATH

# 知识库分类（上传自动分类 / 前端筛选共用）
CATEGORIES = ["课程体系", "师资", "收费", "案例", "机构", "政策", "其他"]

COLLECTION_NAME = "knowledge_chunks"
# 切片参数
MAX_CHARS = 500        # 单 chunk 目标字数
OVERLAP_CHARS = 80     # 相邻 chunk 重叠字数（提高跨段检索召回）
EMBED_BATCH = 16       # 每次 embedding API 调用处理的文本条数
DEFAULT_TOP_K = 5      # 默认检索条数

_client: Optional[PersistentClient] = None
_client_lock = threading.Lock()


# ---------------------------------------------------------------- 基础设施

def _get_client() -> PersistentClient:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = chromadb.PersistentClient(path=CHROMA_PATH)
    return _client


def _get_embedding_provider():
    """获取 embedding Provider；未配置/不支持向量 → 抛 503 可读错误"""
    emb = ai_manager.get_embedding()
    if not emb:
        raise HTTPException(status_code=503, detail="未配置 Embedding 服务，请先在「系统设置 → Embedding」中配置")
    if not emb.supports_embedding:
        raise HTTPException(status_code=503, detail="当前 Embedding Provider 不支持向量化，请更换支持 Embedding 的提供商")
    return emb


def _collection():
    """获取知识库集合；Embedding 模型与上次入库不一致时抛 409 提示重建"""
    client = _get_client()
    emb = _get_embedding_provider()
    model = emb.embedding_model or "default"

    try:
        col = client.get_collection(COLLECTION_NAME)
    except Exception:
        col = client.create_collection(COLLECTION_NAME, metadata={"embedding_model": model})
        return col

    stored = (col.metadata or {}).get("embedding_model")
    if stored and stored != model:
        raise HTTPException(
            status_code=409,
            detail=f"Embedding 模型已从「{stored}」切换为「{model}」，向量维度不一致，请先重建知识库",
        )
    return col


# ---------------------------------------------------------------- 切片

def chunk_text(text: str, max_chars: int = MAX_CHARS, overlap: int = OVERLAP_CHARS) -> List[str]:
    """按段落切分文本为多个 chunk。

    策略：以换行拆段，逐段累积到接近 max_chars 时收尾，当前段若放不下则单独成段。
    相邻 chunk 保留末尾 overlap 字符作为衔接（避免跨段问题被拦腰截断）。
    """
    text = (text or "").strip()
    if not text:
        return []
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: List[str] = []
    current = ""
    for para in paragraphs:
        # 段落本身超长：先按 max_chars 硬切，再继续
        while len(para) > max_chars:
            if current:
                chunks.append(current)
                current = current[-overlap:]
            chunks.append(para[:max_chars])
            para = para[max_chars - overlap:]
        if not current:
            current = para
        elif len(current) + len(para) + 1 <= max_chars:
            current += "\n" + para
        else:
            chunks.append(current)
            current = current[-overlap:] + "\n" + para
    if current:
        chunks.append(current)
    return [c.strip() for c in chunks if c.strip()]


# ---------------------------------------------------------------- Embedding

def _embed_texts(texts: List[str]) -> List[List[float]]:
    """分批调用 embedding API；失败抛 502"""
    emb = _get_embedding_provider()
    vectors: List[List[float]] = []
    try:
        for i in range(0, len(texts), EMBED_BATCH):
            batch = texts[i:i + EMBED_BATCH]
            vectors.extend(emb.embed(batch))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Embedding 调用失败：{e}")
    if not vectors or not vectors[0]:
        raise HTTPException(status_code=502, detail="Embedding 返回为空，请检查模型配置")
    return vectors


# ---------------------------------------------------------------- 入库 / 删除 / 重建

def _index_text(doc_id: int, title: str, category: str, text: str) -> int:
    """将文本切块 + 向量化 + 写入 ChromaDB，返回 chunk 数量"""
    chunks = chunk_text(text)
    if not chunks:
        return 0
    vectors = _embed_texts(chunks)
    ids = [f"doc{doc_id}-c{i}" for i in range(len(chunks))]
    metadatas = [
        {"doc_id": str(doc_id), "doc_title": title, "category": category, "chunk_index": i}
        for i in range(len(chunks))
    ]
    col = _collection()
    col.add(ids=ids, embeddings=vectors, documents=chunks, metadatas=metadatas)
    return len(chunks)


def index_document(db: Session, doc: KnowledgeDoc) -> int:
    """入库单个文档（解析 → 切片 → 向量化）。返回 chunk 数；解析失败抛 400"""
    text, err = document_parser.parse_file(doc.file_path, doc.file_type)
    if err:
        raise HTTPException(status_code=400, detail=err)
    if not text.strip():
        raise HTTPException(status_code=400, detail="文档内容为空，无法入库")
    count = _index_text(doc.id, doc.title, doc.category, text)
    doc.chunk_count = count
    db.commit()
    return count


def delete_document_vectors(doc_id: int):
    """删除指定文档的所有向量（文档删除/重新解析时用）"""
    try:
        col = _collection()
    except HTTPException:
        # Embedding 未配置/集合不存在时无需清理
        return
    try:
        col.delete(where={"doc_id": str(doc_id)})
    except Exception:
        pass  # 集合空或查询失败时忽略，DB 行删除为主


def reparse_document(db: Session, doc: KnowledgeDoc) -> int:
    """重新解析：先清旧向量，再重新入库。返回新 chunk 数"""
    delete_document_vectors(doc.id)
    count = index_document(db, doc)
    return count


def rebuild_kb(db: Session) -> dict:
    """重建知识库：删除整个集合 + 按 active 文档全部重新入库。

    用于 Embedding 模型切换后维度不一致的场景。
    """
    client = _get_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    docs = db.query(KnowledgeDoc).filter(KnowledgeDoc.status == "active").all()
    total = 0
    errors = []
    for doc in docs:
        try:
            total += index_document(db, doc)
            doc.index_status = "done"
            doc.index_error = ""
        except HTTPException as e:
            doc.index_status = "error"
            doc.index_error = str(e.detail)[:200]
            errors.append(f"{doc.title}：{e.detail}")
        db.commit()
    return {"chunk_count": total, "errors": errors}


# ---------------------------------------------------------------- 检索

def search(db: Session, query: str, top_k: int = DEFAULT_TOP_K,
           include_disabled: bool = False) -> List[dict]:
    """向量检索 Top-K。

    include_disabled=False 时仅检索 status=active 的文档（与启用/禁用开关一致）。
    返回 [{doc_id, title, category, chunk_index, snippet, distance}]
    """
    query = (query or "").strip()
    if not query:
        return []
    try:
        col = _collection()
    except HTTPException:
        return []  # Embedding 未配置 → 空结果（调用方优雅降级）
    if col.count() == 0:
        return []

    # 组装 active 文档过滤
    if include_disabled:
        where = None
    else:
        active_ids = [str(r[0]) for r in
                      db.query(KnowledgeDoc.id).filter(KnowledgeDoc.status == "active").all()]
        if not active_ids:
            return []
        where = {"doc_id": {"$in": active_ids}}

    try:
        vecs = _embed_texts([query])
        res = col.query(query_embeddings=vecs, n_results=min(top_k, col.count()),
                        where=where, include=["documents", "metadatas", "distances"])
    except HTTPException:
        raise
    except Exception:
        return []  # 检索异常降级为空，不阻断报告/问答主流程

    items = []
    docs = res.get("documents") or [[]]
    metas = res.get("metadatas") or [[]]
    dists = res.get("distances") or [[]]
    for meta, snippet, dist in zip(metas[0], docs[0], dists[0]):
        if snippet is None or not str(snippet or "").strip():
            continue
        items.append({
            "doc_id": int(meta.get("doc_id", 0)),
            "title": str(meta.get("doc_title") or ""),
            "category": str(meta.get("category") or "其他"),
            "chunk_index": int(meta.get("chunk_index", 0)),
            "snippet": str(snippet),
            "distance": round(float(dist), 4) if dist is not None else None,
        })
    return items


def build_kb_context(results: List[dict], max_chars: int = 3000) -> str:
    """把检索结果拼成 Prompt 用的上下文文本（含来源标题）"""
    if not results:
        return ""
    parts = []
    used = 0
    for r in results:
        block = f"[来自《{r['title']}》]:\n{r['snippet']}"
        used += len(block)
        if used > max_chars and parts:
            break
        parts.append(block)
    return "\n\n".join(parts)


# ---------------------------------------------------------------- LLM 辅助（查询改写 / 自动分类）

def rewrite_query(question: str) -> str:
    """查询改写：先用 LLM 把口语化问题扩写为适合向量检索的关键词组合。

    无 LLM 配置 / 调用失败 → 回退原问题（优雅降级）。
    """
    llm = ai_manager.get_llm()
    if not llm:
        return question
    try:
        prompt = render_prompt("query_rewrite.txt", question=question)
        system = render_prompt("system_prompt.txt")
        text = (llm.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ], temperature=0.2) or "").strip().strip('"\'\n。.')
        first = text.splitlines()[0].strip() if text else ""
        return first[:60] if first else question
    except Exception:
        return question


def classify_document(title: str, text: str) -> str:
    """AI 自动判断文档分类；无 LLM / 无法匹配 → 「其他」"""
    llm = ai_manager.get_llm()
    if not llm:
        return "其他"
    try:
        prompt = render_prompt("category_classify.txt", title=title, text=(text or "")[:1500])
        system = render_prompt("system_prompt.txt")
        out = (llm.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ], temperature=0.2) or "").strip()
        for cat in CATEGORIES:
            if cat in out:
                return cat
        return "其他"
    except Exception:
        return "其他"
