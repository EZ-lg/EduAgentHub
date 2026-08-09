"""
学生管理 API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from backend.models import get_db
from backend.models.student import Student
from backend.models.subject import Subject
from backend.utils.activity import log_activity
from backend.utils.helpers import success_response, now_iso

router = APIRouter(prefix="/api/students", tags=["students"])


def _active_subject_counts(db: Session) -> dict:
    """返回 {student_id: 活跃学科数} 映射，供列表/详情使用"""
    rows = db.query(Subject.student_id, func.count(Subject.id)).filter(
        Subject.status == "active"
    ).group_by(Subject.student_id).all()
    return {sid: cnt for sid, cnt in rows}


def _to_dict_with_subjects(db: Session, student: Student) -> dict:
    """学生 to_dict + 活跃/总学科数"""
    counts = _active_subject_counts(db)
    data = student.to_dict()
    data["active_subjects"] = counts.get(student.id, 0)
    return data


@router.get("")
def list_students(
    search: str = "",
    grade: str = "",
    status: str = "",
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    """获取学生列表（搜索/筛选/分页）"""
    query = db.query(Student)
    if search:
        query = query.filter(
            (Student.name.contains(search)) | (Student.phone.contains(search))
        )
    if grade:
        query = query.filter(Student.grade == grade)
    if status:
        query = query.filter(Student.status == status)
    total = query.count()
    items = query.order_by(Student.updated_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    counts = _active_subject_counts(db)
    result_items = []
    for s in items:
        data = s.to_dict()
        data["active_subjects"] = counts.get(s.id, 0)
        result_items.append(data)
    return success_response({
        "items": result_items,
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.post("")
def create_student(data: dict, db: Session = Depends(get_db)):
    """新建学生"""
    student = Student(
        name=data.get("name", ""),
        gender=data.get("gender", ""),
        grade=data.get("grade", ""),
        school=data.get("school", ""),
        phone=data.get("phone", ""),
        parent_name=data.get("parent_name", ""),
        parent_phone=data.get("parent_phone", ""),
        address=data.get("address", ""),
        source=data.get("source", ""),
        notes=data.get("notes", ""),
    )
    db.add(student)
    db.flush()  # 拿到 id 供活动日志关联
    log_activity(db, "新建学生", f"学生「{student.name}」", student_id=student.id)
    db.commit()
    db.refresh(student)
    return success_response(student.to_dict())


@router.get("/{student_id}")
def get_student(student_id: int, db: Session = Depends(get_db)):
    """获取学生详情"""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    return success_response(_to_dict_with_subjects(db, student))


@router.put("/{student_id}")
def update_student(student_id: int, data: dict, db: Session = Depends(get_db)):
    """更新学生信息"""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    for field in ["name", "gender", "grade", "school", "phone", "parent_name",
                  "parent_phone", "address", "source", "notes"]:
        if field in data:
            setattr(student, field, data[field])
    student.updated_at = now_iso()
    log_activity(db, "编辑学生", f"学生「{student.name}」", student_id=student.id)
    db.commit()
    db.refresh(student)
    return success_response(student.to_dict())


@router.delete("/{student_id}")
def delete_student(student_id: int, db: Session = Depends(get_db)):
    """删除学生（级联删除学科及关联数据）"""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    log_activity(db, "删除学生", f"学生「{student.name}」", student_id=student.id)
    db.delete(student)
    db.commit()
    return success_response({"deleted": True})


@router.put("/{student_id}/status")
def update_student_status(student_id: int, data: dict, db: Session = Depends(get_db)):
    """更新学生状态"""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    status = data.get("status", "")
    if status not in ("active", "completed", "abandoned"):
        raise HTTPException(status_code=400, detail="无效状态")
    student.status = status
    student.updated_at = now_iso()
    label = {"active": "在读", "completed": "已结课", "abandoned": "已放弃"}.get(status, status)
    log_activity(db, "更新学生状态", f"学生「{student.name}」→{label}", student_id=student.id)
    db.commit()
    return success_response(student.to_dict())


# ---------------------------------------------------------------- 档案 AI 对话

def _build_student_profile(student: Student) -> str:
    """学生档案 → 文本（供 AI 对话上下文）"""
    parts = [
        f"姓名：{student.name}",
        f"年级：{student.grade or '未填'}",
        f"学校：{student.school or '未填'}",
        f"性别：{student.gender or '未填'}",
        f"电话：{student.phone or '未填'}",
        f"家长：{student.parent_name or '未填'} {student.parent_phone or ''}".strip(),
        f"地址：{student.address or '未填'}",
        f"来源：{student.source or '未填'}",
        f"状态：{'在读' if student.status == 'active' else ('已结课' if student.status == 'completed' else '已放弃')}",
    ]
    if student.notes:
        parts.append(f"备注：{student.notes}")
    return "\n".join(parts)


def _build_subjects_context(db: Session, student_id: int) -> str:
    """各学科 + 最近报告总结 + 成绩概况 → 文本（供 AI 对话上下文）"""
    from backend.models.ai_conversation import AIConversation
    from backend.models.report import Report
    from backend.models.score import Score

    subjects = db.query(Subject).filter(Subject.student_id == student_id).all()
    if not subjects:
        return ""
    lines = []
    for sub in subjects:
        status_txt = "活跃" if sub.status == "active" else "已停用"
        line = f"- {sub.name}（{status_txt}）"
        # 最近报告总结
        report = db.query(Report).filter(
            Report.subject_id == sub.id
        ).order_by(Report.created_at.desc()).first()
        if report:
            try:
                import json
                content = json.loads(report.content_json or "{}")
                if isinstance(content, dict) and content.get("summary"):
                    line += f"\n  最近学情总结：{str(content['summary'])[:200]}"
            except (json.JSONDecodeError, TypeError):
                pass
        # 成绩概况
        scores = db.query(Score).filter(Score.subject_id == sub.id).order_by(Score.exam_date.desc()).all()
        if scores:
            recent = scores[:3]
            score_txt = "，".join(f"{s.exam_name or s.exam_date[:10]} {s.score}/{s.total_score}" for s in recent)
            line += f"\n  最近成绩：{score_txt}"
        else:
            line += "\n  成绩：暂无"
        lines.append(line)
    return "\n".join(lines)


@router.post("/{student_id}/chat")
def student_chat(student_id: int, data: dict = None, db: Session = Depends(get_db)):
    """基于学生档案 + 各学科学情回答教务/家长提问。

    body: {messages: [{role: 'user'|'ai', content}]}，messages 为前端维护的完整历史。
    """
    from backend.ai.manager import ai_manager
    from backend.ai.prompts.prompt_loader import render_prompt

    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")

    if not ai_manager.is_configured("llm"):
        raise HTTPException(status_code=503, detail="AI 服务未配置，请先在系统设置中配置 LLM")

    messages = (data or {}).get("messages") or []
    if not isinstance(messages, list):
        messages = []
    # 取最后一条用户消息作为提问
    last_user = ""
    history = []
    for m in messages:
        role = str(m.get("role") or "").lower()
        content = str(m.get("content") or "").strip()
        if not content:
            continue
        if role in ("user", "human"):
            last_user = content
            history.append({"role": "user", "content": content})
        elif role in ("ai", "assistant"):
            history.append({"role": "ai", "content": content})
    if not last_user:
        raise HTTPException(status_code=400, detail="缺少用户提问内容")

    llm = ai_manager.get_llm()
    prompt = render_prompt(
        "student_chat.txt",
        student_name=student.name,
        student_profile=_build_student_profile(student),
        subjects_context=_build_subjects_context(db, student_id),
        history=history[:-1] if history else [],  # 历史不含最后一条（已单独放 last_message）
        last_message=last_user,
    )
    try:
        reply = llm.chat([
            {"role": "system", "content": render_prompt("system_prompt.txt")},
            {"role": "user", "content": prompt},
        ]) or ""
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 调用失败：{e}")
    return success_response({"reply": reply.strip()})
