"""
操作日志埋点工具 — 供工作台「最近活动」使用

用法：在各写端点调用 log_activity(db, ...)，随后由该端点的 db.commit() 一并写入。
日志只需存 id，名称在工作台 activities 接口 join 渲染，避免各处重复查名。
"""
from sqlalchemy.orm import Session

from backend.models.activity_log import ActivityLog


def log_activity(
    db: Session,
    action: str,
    detail: str = "",
    student_id: int = None,
    subject_id: int = None,
):
    """插入一条操作日志（不自行 commit，随调用方事务一并提交）"""
    db.add(ActivityLog(
        action=action,
        detail=detail or "",
        student_id=student_id,
        subject_id=subject_id,
    ))
