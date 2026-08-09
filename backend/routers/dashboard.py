"""
工作台 API（P9 完善：统计卡片 + 学生看板 + 趋势 + 学科分布 + 最近活动）

- /api/dashboard/stats          统计卡片（在读/活跃学科/本月新增/待处理/教师/总数）
- /api/dashboard/board          学生看板（按状态分列，含活跃学科名）
- /api/dashboard/trend          近 6 个月新增学生趋势（供图表）
- /api/dashboard/subject-dist   学科分布（活跃学科数量 Top，供图表）
- /api/dashboard/activities     最近活动（join 学生/学科名渲染）
"""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models import get_db
from backend.models.activity_log import ActivityLog
from backend.models.course_plan import CoursePlan
from backend.models.report import Report
from backend.models.student import Student
from backend.models.subject import Subject
from backend.models.teacher import Teacher
from backend.utils.helpers import success_response

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

STATUS_LABEL = {"active": "在读", "completed": "已结课", "abandoned": "已放弃"}


def _active_subject_map(db: Session) -> dict:
    """返回 {student_id: [活跃学科名]}，供学生卡片展示"""
    rows = db.query(Subject.student_id, Subject.name).filter(Subject.status == "active").all()
    result = {}
    for sid, name in rows:
        result.setdefault(sid, []).append(name)
    return result


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """统计卡片"""
    active_students = db.query(Student).filter(Student.status == "active").count()
    active_subjects = db.query(Subject).filter(Subject.status == "active").count()
    total_students = db.query(Student).count()
    teachers = db.query(Teacher).count()
    draft_reports = db.query(Report).filter(Report.status == "draft").count()
    month_prefix = datetime.now().strftime("%Y-%m")
    new_students_this_month = db.query(Student).filter(
        Student.created_at.startswith(month_prefix)).count()
    return success_response({
        "active_students": active_students,
        "active_subjects": active_subjects,
        "new_students_this_month": new_students_this_month,
        "total_students": total_students,
        "teachers": teachers,
        "pending_reports": draft_reports,
    })


@router.get("/board")
def get_board(db: Session = Depends(get_db)):
    """学生看板：按状态分列，每列学生卡片（姓名/年级/活跃学科/最近更新）"""
    students = db.query(Student).order_by(Student.updated_at.desc()).limit(60).all()
    subj_map = _active_subject_map(db)
    board = {"active": [], "completed": [], "abandoned": []}
    for s in students:
        card = {
            "id": s.id,
            "name": s.name,
            "grade": s.grade,
            "status": s.status,
            "subjects": subj_map.get(s.id, []),
            "updated_at": s.updated_at,
        }
        board.setdefault(s.status, []).append(card)
    return success_response(board)


@router.get("/trend")
def get_trend(db: Session = Depends(get_db)):
    """近 6 个月新增学生趋势：[{label: '2026-03', count: N}]"""
    today = datetime.now()
    pairs = []
    y, m = today.year, today.month
    for _ in range(6):
        pairs.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    pairs.reverse()
    trend = []
    for y, m in pairs:
        prefix = f"{y:04d}-{m:02d}"
        count = db.query(Student).filter(Student.created_at.startswith(prefix)).count()
        trend.append({"label": f"{m}月" if y == today.year else f"{y}/{m}", "count": count})
    return success_response(trend)


@router.get("/subject-dist")
def get_subject_dist(db: Session = Depends(get_db)):
    """学科分布：活跃学科数量 Top6（含「其他」合并）"""
    rows = db.query(Subject.name, func.count(Subject.id)).filter(
        Subject.status == "active"
    ).group_by(Subject.name).order_by(func.count(Subject.id).desc()).limit(6).all()
    return success_response([{"name": name, "value": cnt} for name, cnt in rows])


@router.get("/activities")
def get_activities(page: int = 1, page_size: int = 20, db: Session = Depends(get_db)):
    """最近活动（join 学生/学科名，供前端直接渲染）"""
    activities = db.query(ActivityLog).order_by(
        ActivityLog.created_at.desc()
    ).offset((page - 1) * page_size).limit(page_size).all()
    result = []
    for a in activities:
        d = a.to_dict()
        if a.subject_id:
            subj = db.get(Subject, a.subject_id)
            if subj:
                d["subject_name"] = subj.name
                stu = db.get(Student, subj.student_id)
                if stu:
                    d["student_name"] = stu.name
        elif a.student_id:
            stu = db.get(Student, a.student_id)
            if stu:
                d["student_name"] = stu.name
        result.append(d)
    return success_response(result)
