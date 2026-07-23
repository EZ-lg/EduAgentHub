"""
知识库 API（P8 实现完整逻辑）
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.models import get_db
from backend.models.knowledge_doc import KnowledgeDoc
from backend.utils.helpers import success_response, now_iso

router = APIRouter(prefix="/api/knowledge-docs", tags=["knowledge_base"])


@router.get("")
def list_docs(category: str = "", db: Session = Depends(get_db)):
    """知识库列表"""
    query = db.query(KnowledgeDoc)
    if category:
        query = query.filter(KnowledgeDoc.category == category)
    docs = query.order_by(KnowledgeDoc.created_at.desc()).all()
    return success_response([d.to_dict() for d in docs])


@router.post("/upload")
def upload_doc(data: dict = None, db: Session = Depends(get_db)):
    """上传文档（P8 实现解析+入库）"""
    return success_response({"info": "文档上传功能将在 P8 实现"})


@router.get("/{doc_id}")
def get_doc(doc_id: int, db: Session = Depends(get_db)):
    """文档详情"""
    doc = db.query(KnowledgeDoc).filter(KnowledgeDoc.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return success_response(doc.to_dict())


@router.delete("/{doc_id}")
def delete_doc(doc_id: int, db: Session = Depends(get_db)):
    """删除文档"""
    doc = db.query(KnowledgeDoc).filter(KnowledgeDoc.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    db.delete(doc)
    db.commit()
    return success_response({"deleted": True})


@router.put("/{doc_id}/status")
def toggle_doc_status(doc_id: int, data: dict, db: Session = Depends(get_db)):
    """启用/禁用"""
    doc = db.query(KnowledgeDoc).filter(KnowledgeDoc.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    doc.status = data.get("status", "active")
    db.commit()
    return success_response(doc.to_dict())


@router.post("/{doc_id}/reparse")
def reparse_doc(doc_id: int, db: Session = Depends(get_db)):
    """重新解析（P8 实现）"""
    return success_response({"info": "重新解析功能将在 P8 实现"})


@router.post("/search")
def search_docs(data: dict, db: Session = Depends(get_db)):
    """检索测试（P8 实现向量检索）"""
    return success_response({"info": "检索功能将在 P8 实现"})
