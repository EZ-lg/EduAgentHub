"""
寒暑假班（term schedule）工具 — 日期计算 + 班期冲突检测

寒暑假班模式：每天固定 1 节（daily_start ~ daily_end + classroom_id），周日休息。
- 班期：start_date 起，第 total_lessons 个上课日（跳过周日）为 end_date
- 冲突：班期内每个上课日，该班的（时段 + 教室/教师/学生）不得被其他已确认课占用
  占用源：学期班 active 周循环课 + 其他 active 寒暑假班
"""
from datetime import datetime, timedelta

from backend.models.class_ import Class
from backend.models.class_schedule import ClassSchedule
from backend.models.class_student import ClassStudent


def _parse(d: str):
    try:
        return datetime.strptime(d, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def _to_min(t: str) -> int:
    try:
        h, m = str(t).split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return 0


def _overlap(a_s: str, a_e: str, b_s: str, b_e: str) -> bool:
    return _to_min(a_s) < _to_min(b_e) and _to_min(b_s) < _to_min(a_e)


def compute_end_date(start_date: str, total_lessons: int) -> str:
    """从 start_date 起跳过周日，第 total_lessons 个上课日的日期"""
    d = _parse(start_date)
    if not d:
        return start_date
    count = 0
    while count < total_lessons:
        if d.weekday() != 6:  # 跳过周日
            count += 1
        d += timedelta(days=1)
    return (d - timedelta(days=1)).strftime("%Y-%m-%d")


def lesson_dates(start_date: str, end_date: str):
    """班期内所有上课日（跳过周日），返回 [(date_str, weekday)]"""
    s, e = _parse(start_date), _parse(end_date)
    if not s or not e:
        return []
    result = []
    d = s
    while d <= e:
        if d.weekday() != 6:
            result.append((d.strftime("%Y-%m-%d"), d.weekday()))
        d += timedelta(days=1)
    return result


def _class_students(db, class_id):
    rows = db.query(ClassStudent).filter(ClassStudent.class_id == class_id).all()
    return [r.student_id for r in rows]


def check_term_conflicts(db, cls_id: int) -> list:
    """检查某寒暑假班班期内的全部冲突。

    返回 [{date, weekday, type, with_class_id, with_class_name, message}]
    """
    cls = db.query(Class).filter(Class.id == cls_id).first()
    if not cls or cls.term_type != "summer_winter":
        return []
    if not cls.start_date or not cls.daily_start or not cls.daily_end:
        return []
    end_date = cls.end_date or compute_end_date(cls.start_date, cls.total_lessons or 0)
    students = set(_class_students(db, cls.id))
    conflicts = []

    term_schedules = db.query(ClassSchedule).filter(ClassSchedule.status == "active").all()
    other_terms = db.query(Class).filter(
        Class.term_type == "summer_winter", Class.status == "active", Class.id != cls.id).all()

    def _add(day, weekday, ctype, other_id, other_name, msg):
        conflicts.append({
            "date": day, "weekday": weekday, "type": ctype,
            "with_class_id": other_id, "with_class_name": other_name,
            "message": msg,
        })

    for day, weekday in lesson_dates(cls.start_date, end_date):
        # a) 学期班周循环课
        for s in term_schedules:
            if s.weekday != weekday:
                continue
            if not _overlap(cls.daily_start, cls.daily_end, s.start_time, s.end_time):
                continue
            other_name = _class_name(db, s.class_id)
            if cls.classroom_id and s.classroom_id and cls.classroom_id == s.classroom_id:
                _add(day, weekday, "教室", s.class_id, other_name, f"{day} 教室被「{other_name}」占用")
            if cls.teacher_id and s.teacher_id and cls.teacher_id == s.teacher_id:
                _add(day, weekday, "教师", s.class_id, other_name, f"{day} 教师已有课")
            shared = students & set(_class_students(db, s.class_id))
            if shared:
                _add(day, weekday, "学生", s.class_id, other_name, f"{day} 学生同时在多个班上课")
        # b) 其他寒暑假班
        for o in other_terms:
            if not o.start_date or not o.daily_start or not o.daily_end:
                continue
            o_end = o.end_date or compute_end_date(o.start_date, o.total_lessons or 0)
            if not (o.start_date <= day <= o_end):
                continue
            if not _overlap(cls.daily_start, cls.daily_end, o.daily_start, o.daily_end):
                continue
            if cls.classroom_id and o.classroom_id and cls.classroom_id == o.classroom_id:
                _add(day, weekday, "教室", o.id, o.name, f"{day} 教室被「{o.name}」占用")
            if cls.teacher_id and o.teacher_id and cls.teacher_id == o.teacher_id:
                _add(day, weekday, "教师", o.id, o.name, f"{day} 教师已有课")
            shared = students & set(_class_students(db, o.id))
            if shared:
                _add(day, weekday, "学生", o.id, o.name, f"{day} 学生同时在多个班上课")

    return conflicts


def _class_name(db, class_id: int) -> str:
    c = db.query(Class).filter(Class.id == class_id).first()
    return c.name if c else ""
