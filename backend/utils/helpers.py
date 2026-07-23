"""
通用工具函数
"""
from datetime import datetime


def now_iso() -> str:
    """返回当前时间的 ISO 格式字符串"""
    return datetime.now().isoformat()


def success_response(data=None) -> dict:
    """统一成功响应"""
    return {"success": True, "data": data}


def error_response(error: str) -> dict:
    """统一错误响应"""
    return {"success": False, "error": error}
