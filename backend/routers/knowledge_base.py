"""
知识库 API（P8 完整实现 + 加分项）

- /api/knowledge-docs/*  知识库管理：上传（后台异步入库）/ 列表 / 预览 / 启用停用 / 删除 / 重新解析 / 检索测试 / 重建
- /api/knowledge/*       智能问答：预设问题 + 自由提问（RAG + 查询改写）+ 问答历史持久化
"""
import json
import os
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from backend.ai.manager import ai_manager
from backend.ai.prompts.prompt_loader import render_prompt
from backend.models import get_db
from backend.models.knowledge_doc import KnowledgeDoc
from backend.models.qa_history import QaHistory
from backend.services import document_parser, kb_service
from backend.utils.activity import log_activity
from backend.utils.helpers import success_response
from config import UPLOAD_DIR

router = APIRouter(prefix="/api/knowledge-docs", tags=["knowledge_base"])
qa_router = APIRouter(prefix="/api/knowledge", tags=["knowledge_qa"])

# 知识库问答预设问题（F10.1）
QA_PRESETS = [
    "初二数学主要学什么",
    "收费标准是怎样的",
    "机构开设哪些课程",
    "如何联系机构",
]

CATEGORY_ALIASES = {"markdown": "md"}


# ---------------------------------------------------------------- 工具

def _get_doc(db: Session, doc_id: int) -> KnowledgeDoc:
    doc = db.get(KnowledgeDoc, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc


def _safe_stem(name: str, fallback: str = "doc") -> str:
    s = re.sub(r'[\\/:*?"<>|\r\n]', "_", name or "").strip()
    return (s[:60] or fallback)


def _save_upload(content: bytes, filename: str) -> str:
    """保存上传文件到 data/uploads/，返回绝对路径"""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    stem = Path(filename).stem or "doc"
    save_name = f"kb_{datetime.now().strftime('%Y%m%d%H%M%S')}_{_safe_stem(stem)}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, save_name)
    with open(file_path, "wb") as f:
        f.write(content)
    return file_path


# ---------------------------------------------------------------- 知识库管理

@router.get("")
def list_docs(category: str = "", db: Session = Depends(get_db)):
    """知识库列表（按分类筛选，最新在前）"""
    query = db.query(KnowledgeDoc)
    if category:
        query = query.filter(KnowledgeDoc.category == category)
    docs = query.order_by(KnowledgeDoc.created_at.desc()).all()
    return success_response([d.to_dict() for d in docs])


def _ingest_doc_async(doc_id: int, auto_category: bool = False):
    """后台入库任务：解析 → （可选 AI 自动分类）→ 切片 → 向量化。

    请求返回后独立运行，需自建 DB Session。失败时文档标记 error + 错误信息。
    """
    from backend.models import SessionLocal
    db = SessionLocal()
    try:
        doc = db.get(KnowledgeDoc, doc_id)
        if not doc:
            return
        doc.index_status = "processing"
        db.commit()
        text, err = document_parser.parse_file(doc.file_path, doc.file_type)
        if err:
            raise ValueError(err)
        if auto_category:
            doc.category = kb_service.classify_document(doc.title, text)
            db.commit()
        count = kb_service.index_document(db, doc)  # 内部设置 chunk_count 并 commit
        doc.index_status = "done"
        doc.index_error = ""
        log_activity(db, "上传知识库文档", f"《{doc.title}》（{count} 个切片）")
        db.commit()
    except Exception as e:
        db.rollback()
        doc = db.get(KnowledgeDoc, doc_id)
        if doc:
            doc.index_status = "error"
            doc.index_error = str(e)[:200]
            db.commit()
    finally:
        db.close()


@router.post("/upload")
def upload_doc(
    file: UploadFile = File(...),
    category: str = Form("其他"),
    title: str = Form(""),
    auto_category: bool = Form(False),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    """上传文档：保存文件 → 立即返回（后台异步入库）。

    auto_category=True 时由 AI 根据文档内容自动判断分类（解析后回填）。
    """
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    fmt = CATEGORY_ALIASES.get(ext, ext)
    if fmt not in document_parser.SUPPORTED_EXTS:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式：{ext or '未知'}（支持 PDF / Word / TXT / Markdown）")

    content = file.file.read()
    if len(content) > document_parser.MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件超过 50MB 上限")

    file_path = _save_upload(content, filename)
    doc_category = "待分类" if auto_category else ((category or "").strip() or "其他")
    doc = KnowledgeDoc(
        title=(title or "").strip() or Path(filename).stem,
        category=doc_category,
        file_path=file_path,
        file_type=fmt,
        chunk_count=0,
        status="active",
        index_status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    background_tasks.add_task(_ingest_doc_async, doc.id, auto_category)
    return success_response(doc.to_dict())


@router.post("/rebuild")
def rebuild(db: Session = Depends(get_db)):
    """重建知识库：清空向量后按全部 active 文档重新入库（Embedding 模型切换后使用）"""
    result = kb_service.rebuild_kb(db)
    return success_response(result)


@router.get("/{doc_id}")
def get_doc(doc_id: int, db: Session = Depends(get_db)):
    """文档详情"""
    return success_response(_get_doc(db, doc_id).to_dict())


@router.get("/{doc_id}/preview")
def preview_doc(doc_id: int, db: Session = Depends(get_db)):
    """文档预览：重新解析文件返回纯文本（截断到 8000 字，避免大响应）"""
    doc = _get_doc(db, doc_id)
    text, err = document_parser.parse_file(doc.file_path, doc.file_type)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return success_response({"text": text[:8000], "total_chars": len(text)})


@router.delete("/{doc_id}")
def delete_doc(doc_id: int, db: Session = Depends(get_db)):
    """删除文档：删 DB 行 + 删向量 + 删源文件"""
    doc = _get_doc(db, doc_id)
    kb_service.delete_document_vectors(doc.id)
    file_path = doc.file_path
    log_activity(db, "删除知识库文档", f"《{doc.title}》")
    db.delete(doc)
    db.commit()
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass
    return success_response({"deleted": True})


@router.put("/{doc_id}/status")
def toggle_doc_status(doc_id: int, data: dict, db: Session = Depends(get_db)):
    """启用/禁用（向量保留，检索时按 active 过滤）"""
    doc = _get_doc(db, doc_id)
    doc.status = "active" if data.get("status") == "active" else "disabled"
    db.commit()
    return success_response(doc.to_dict())


@router.post("/{doc_id}/reparse")
def reparse_doc(doc_id: int, db: Session = Depends(get_db)):
    """重新解析：清旧向量 → 重新切片入库（同步；入库失败标记 error 由前端展示）"""
    doc = _get_doc(db, doc_id)
    try:
        count = kb_service.reparse_document(db, doc)
        doc.index_status = "done"
        doc.index_error = ""
        log_activity(db, "重新解析知识库文档", f"《{doc.title}》")
        db.commit()
    except HTTPException:
        raise
    except Exception as e:
        doc.index_status = "error"
        doc.index_error = str(e)[:200]
        db.commit()
        raise HTTPException(status_code=400, detail=f"重新解析失败：{e}")
    return success_response(doc.to_dict())


@router.post("/search")
def search_docs(data: dict, db: Session = Depends(get_db)):
    """检索测试（F9.8）：向量检索 Top-K（原始查询，不改写）"""
    query = (data.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="请输入检索内容")
    top_k = max(1, min(int(data.get("top_k") or 5), 20))
    include_disabled = bool(data.get("include_disabled"))
    results = kb_service.search(db, query, top_k=top_k, include_disabled=include_disabled)
    return success_response(results)


# ---------------------------------------------------------------- 智能问答

@qa_router.get("/qa/presets")
def get_qa_presets():
    """预设问题（F10.1）"""
    return success_response(QA_PRESETS)


@qa_router.get("/qa/history")
def get_qa_history(db: Session = Depends(get_db)):
    """问答历史（最近 30 条，早的在前）"""
    items = db.query(QaHistory).order_by(QaHistory.created_at.desc()).limit(30).all()
    items.reverse()
    return success_response([i.to_dict() for i in items])


@qa_router.delete("/qa/history")
def clear_qa_history(db: Session = Depends(get_db)):
    """清空问答历史"""
    db.query(QaHistory).delete()
    db.commit()
    return success_response({"deleted": True})


@qa_router.post("/qa")
def qa(data: dict, db: Session = Depends(get_db)):
    """知识库智能问答（F10.2）：查询改写 → 检索 Top-5 → RAG Prompt → LLM 回答 + 引用来源 + 历史留存"""
    question = (data.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="请输入问题")

    # 查询改写：仅当知识库真实可用时执行（避免白耗一次 LLM 调用）
    query = question
    if ai_manager.get_embedding() is not None:
        has_active = db.query(KnowledgeDoc).filter(KnowledgeDoc.status == "active").count() > 0
        if has_active:
            query = kb_service.rewrite_query(question)

    results = kb_service.search(db, query, top_k=5)
    kb_context = kb_service.build_kb_context(results) or "（知识库中未检索到相关内容，请基于你的常识作答，并明确说明这一点）"

    llm = ai_manager.get_llm()
    if not llm:
        raise HTTPException(status_code=503, detail="AI 服务未配置，请先在系统设置中配置 LLM")
    prompt = render_prompt("knowledge_qa.txt", question=question, kb_context=kb_context)
    try:
        system = render_prompt("system_prompt.txt")
        answer = llm.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ], temperature=0.3) or ""
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 调用失败：{e}")

    references = [
        {"doc_id": r["doc_id"], "title": r["title"], "category": r["category"],
         "snippet": r["snippet"], "distance": r["distance"]}
        for r in results
    ]

    # 历史留存（仅成功问答）
    history = QaHistory(
        question=question,
        answer=answer,
        references_json=json.dumps(references, ensure_ascii=False),
    )
    db.add(history)
    db.commit()

    return success_response({"answer": answer, "references": references})
