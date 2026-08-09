"""
知识库文档模型
"""
from sqlalchemy import Column, Integer, String
from backend.models import Base
from backend.utils.helpers import now_iso


class KnowledgeDoc(Base):
    __tablename__ = "knowledge_docs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    category = Column(String, default="其他")
    file_path = Column(String, default="")
    file_type = Column(String, default="")
    chunk_count = Column(Integer, default=0)
    status = Column(String, default="active")  # active / disabled
    # 异步入库状态：pending / processing / done / error（P8 加分3；历史数据默认 done）
    index_status = Column(String, default="done")
    index_error = Column(String, default="")
    created_at = Column(String, default=now_iso)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "file_path": self.file_path,
            "file_type": self.file_type,
            "chunk_count": self.chunk_count,
            "status": self.status,
            "index_status": self.index_status or "done",
            "index_error": self.index_error or "",
            "created_at": self.created_at,
        }
