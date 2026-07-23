"""
全局配置管理
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
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "tutoring.db")
CHROMA_PATH = os.path.join(DATA_DIR, "chroma_data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
EXPORT_DIR = os.path.join(DATA_DIR, "exports")

# 数据库连接 URL
DATABASE_URL = f"sqlite:///{DB_PATH}"

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CHROMA_PATH, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)

# 服务器配置
DEFAULT_PORT = 8888
HOST = "127.0.0.1"

# 前端目录
if getattr(sys, 'frozen', False):
    FRONTEND_DIR = os.path.join(sys._MEIPASS, "frontend")
else:
    FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
