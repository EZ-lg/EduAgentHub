"""
全局配置管理（2.0 可迁移化）

设计：所有路径/URL/端口均支持环境变量覆盖（服务器部署优先用环境变量），
默认值保持单机/exe 行为不变。环境变量命名统一前缀 EDU_：
  EDU_DATA_DIR      数据目录（服务器部署映射到持久卷）
  EDU_DATABASE_URL  数据库连接 URL（可切 PostgreSQL 等）
  EDU_CHROMA_PATH   ChromaDB 向量库目录
  EDU_FRONTEND_DIR  前端静态目录（默认开发时用项目 frontend）
  EDU_HOST          绑定主机（服务器部署设 0.0.0.0）
  EDU_PORT          监听端口
"""
import os
import sys


def get_base_dir():
    """获取应用基础目录（exe运行时的同级目录，或开发时的项目目录）"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后运行
        return os.path.dirname(sys.executable)
    else:
        # 开发模式
        return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = get_base_dir()

# 数据目录：优先环境变量，默认 exe/项目 同级 data
DATA_DIR = os.getenv("EDU_DATA_DIR", os.path.join(BASE_DIR, "data"))
DB_PATH = os.path.join(DATA_DIR, "tutoring.db")
CHROMA_PATH = os.getenv("EDU_CHROMA_PATH", os.path.join(DATA_DIR, "chroma_data"))
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
EXPORT_DIR = os.path.join(DATA_DIR, "exports")

# 数据库连接 URL：优先环境变量（服务器可切 PostgreSQL），默认 SQLite
DATABASE_URL = os.getenv("EDU_DATABASE_URL", f"sqlite:///{DB_PATH}")

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CHROMA_PATH, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)

# 服务器配置：环境变量可覆盖（服务器绑 0.0.0.0），默认 127.0.0.1:8888
HOST = os.getenv("EDU_HOST", "127.0.0.1")
PORT = int(os.getenv("EDU_PORT", "8888"))
DEFAULT_PORT = PORT  # 兼容旧引用

# 前端目录
if getattr(sys, 'frozen', False):
    FRONTEND_DIR = os.path.join(sys._MEIPASS, "frontend")
else:
    FRONTEND_DIR = os.getenv("EDU_FRONTEND_DIR", os.path.join(BASE_DIR, "frontend"))
