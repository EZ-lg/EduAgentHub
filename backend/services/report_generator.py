"""
P5 报告生成 — 业务逻辑

数据流：学科 + 学生 + 最近 completed 会话的学情总结（conversation_summary）
  → report_generation.txt → LLM → 4 节 JSON + 课程规划 plan 数组
  → 建 Report 行（content_json / kb_references_json） + 建 CoursePlan 行（course_plan_id 关联，旧 active 归档）

设计要点：
- content_json.sections = {basic_info, level_analysis, course_plan, study_advice}
  每节 {title, content, ai_generated, last_modified}；course_plan 额外含 plan 数组（可编辑表格数据）
- RAG 优雅降级：embedding 未配置 / 无 active 知识文档 / ChromaDB 未接入（P8）→ kb_context 传空串、kb_references 空数组，报告照常生成
- 重新生成：{extra_info, section?}，section 缺省全量重生成，否则只重生成该节
- 课程规划版本纪律：每次规划变更（含 course_plan 节重生成）都新建 CoursePlan 版本并归档旧 active
"""
import json
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.ai.manager import ai_manager
from backend.ai.prompts.prompt_loader import render_prompt
from backend.models.ai_conversation import AIConversation
from backend.models.course_plan import CoursePlan
from backend.models.knowledge_doc import KnowledgeDoc
from backend.models.report import Report
from backend.models.student import Student
from backend.models.subject import Subject
from backend.services.conversation_service import SUMMARY_PREFIX, _extract_json
from backend.utils.helpers import now_iso

REPORT_TEMPERATURE = 0.3
PLAN_MAX_ROWS = 20
# 章式计划：10 个固定章节前缀 + 默认标题；summary/plan/conclusion 为独立字段
CHAPTER_PREFIXES = ("一、", "二、", "三、", "四、", "五、", "六、", "七、", "八、", "九、", "十、")
DEFAULT_CHAPTER_TITLES = {
    "一、": "一、当前情况与目标",
    "二、": "二、目标达成路径",
    "三、": "三、核心战略",
    "四、": "四、方法论科学原理",
    "五、": "五、两阶段执行框架",
    "六、": "六、本学科落地规划",
    "七、": "七、学期节奏与每周安排",
    "八、": "八、时间管理与精力保护",
    "九、": "九、评估与复盘机制",
    "十、": "十、心态建设",
}
REGEN_KEYS = ("summary", "plan", "conclusion")


# ---------------------------------------------------------------- 私有工具

def _get_subject(db: Session, subject_id: int) -> Subject:
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="学科不存在")
    return subject


def _get_report(db: Session, report_id: int) -> Report:
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    return report


def _load_json(text, default):
    try:
        data = json.loads(text or "null")
        return data if isinstance(data, (dict, list)) else default
    except (json.JSONDecodeError, TypeError):
        return default


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _call_llm(prompt: str, temperature: float = REPORT_TEMPERATURE) -> str:
    """统一 LLM 调用：未配置抛 503，失败抛 502"""
    llm = ai_manager.get_llm()
    if not llm:
        raise HTTPException(status_code=503, detail="AI 服务未配置，请先在系统设置中配置 LLM")
    try:
        system = render_prompt("system_prompt.txt")
        return llm.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ], temperature=temperature) or ""
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 调用失败：{e}")


def _conversation_summary(db: Session, subject_id: int, conversation_id: int = None) -> str:
    """取指定（或该学科最近）completed 会话的学情总结，剥掉【学情总结】前缀"""
    conv = None
    if conversation_id:
        conv = db.get(AIConversation, conversation_id)
        if conv and (conv.subject_id != subject_id or conv.status != "completed"):
            conv = None
    if conv is None:
        conv = db.query(AIConversation).filter(
            AIConversation.subject_id == subject_id,
            AIConversation.status == "completed",
        ).order_by(AIConversation.updated_at.desc()).first()
    if conv is None:
        return "（尚未进行过 AI 学情采集对话，可结合学生档案信息撰写）"

    try:
        msgs = json.loads(conv.messages_json or "[]")
    except (json.JSONDecodeError, TypeError):
        msgs = []
    for m in reversed(msgs if isinstance(msgs, list) else []):
        if m.get("role") == "ai":
            content = m.get("content", "")
            if content.startswith(SUMMARY_PREFIX):
                return content[len(SUMMARY_PREFIX):]
            return content
    return "（对话中暂无有效学情总结）"


def _build_student_info(student: Student) -> str:
    parts = []
    if student.grade:
        parts.append(f"年级：{student.grade}")
    if student.school:
        parts.append(f"学校：{student.school}")
    if student.gender:
        parts.append(f"性别：{student.gender}")
    if student.parent_name:
        parts.append(f"家长：{student.parent_name}")
    if student.parent_phone:
        parts.append(f"家长电话：{student.parent_phone}")
    if student.notes:
        parts.append(f"备注：{student.notes}")
    return "\n".join(parts) if parts else "（无额外学生信息）"


def _retrieve_kb_context(db: Session, query: str):
    """RAG 检索（优雅降级）。

    P5 阶段 ChromaDB 未接入（P8 实现）：
    - embedding 未配置 / 无 active 知识文档 / 基础设施未就绪 → 一律返回 ("", [])
    - P8 时替换此函数为真实向量检索（签名不变，返回 (context_text, [{"title","category","snippet"}])）
    """
    embedding_ok = ai_manager.get_embedding() is not None
    doc_count = db.query(KnowledgeDoc).filter(KnowledgeDoc.status == "active").count()
    if not embedding_ok or doc_count == 0:
        return "", []
    # TODO(P8): ChromaDB 向量检索 Top-5 → 拼 context_text + kb_references
    return "", []



def _parse_plan(plan) -> list:
    """清洗课程规划行：字段齐全、teacher_id 归一化、截断上限"""
    if not isinstance(plan, list):
        return []
    rows = []
    for item in plan[:PLAN_MAX_ROWS]:
        if not isinstance(item, dict):
            continue
        tid = item.get("teacher_id")
        if tid in (None, "", "null", "None"):
            tid = None
        else:
            try:
                tid = int(tid)
            except (TypeError, ValueError):
                tid = None
        rows.append({
            "lesson": str(item.get("lesson") or ""),
            "content": str(item.get("content") or ""),
            "hours": item.get("hours"),
            "teacher_id": tid,
            "teacher_name": str(item.get("teacher_name") or ""),
            "schedule": str(item.get("schedule") or ""),
            "notes": str(item.get("notes") or ""),
        })
    return rows


def _parse_chapter(data) -> dict:
    """标准化一个章节：{title, content, ai_generated, last_modified}"""
    if not isinstance(data, dict):
        return {"title": "", "content": "", "ai_generated": True, "last_modified": now_iso()}
    return {
        "title": str(data.get("title") or ""),
        "content": str(data.get("content") or ""),
        "ai_generated": True,
        "last_modified": now_iso(),
    }


def _parse_chapters(data_chapters) -> list:
    """解析 chapters：按「一、」~「十、」前缀对齐，缺章补齐"""
    by_prefix = {}
    if isinstance(data_chapters, list):
        for ch in data_chapters:
            if not isinstance(ch, dict):
                continue
            t = str(ch.get("title") or "")
            if len(t) >= 2 and t[:2] in CHAPTER_PREFIXES:
                by_prefix[t[:2]] = ch
    result = []
    for prefix, default_title in DEFAULT_CHAPTER_TITLES.items():
        item = _parse_chapter(by_prefix.get(prefix))
        if not item["title"]:
            item["title"] = default_title
        result.append(item)
    return result


def _parse_report_output(text: str) -> dict:
    """解析报告生成输出 → {title, subtitle, summary, chapters, plan, conclusion, kb_references}；失败抛 502"""
    data = _extract_json(text)
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="AI 返回格式不正确，请重新生成")
    kb = data.get("kb_references")
    return {
        "title": str(data.get("title") or ""),
        "subtitle": str(data.get("subtitle") or ""),
        "summary": str(data.get("summary") or ""),
        "chapters": _parse_chapters(data.get("chapters")),
        "plan": _parse_plan(data.get("plan")),
        "conclusion": str(data.get("conclusion") or ""),
        "kb_references": kb if isinstance(kb, list) else [],
    }


def _parse_regenerate_output(text: str, section: str) -> dict:
    """解析重新生成输出（章节级）"""
    data = _extract_json(text)
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="AI 返回格式不正确，请重新生成")
    if not section:
        return _parse_report_output(text)
    if section in ("summary", "conclusion"):
        if section in data and str(data[section]).strip():
            return {section: str(data[section])}
        raise HTTPException(status_code=502, detail=f"AI 未返回「{section}」，请重新生成")
    if section == "plan":
        return {"plan": _parse_plan(data.get("plan"))}
    # 章节前缀（一、~十、）
    prefix = section[:2]
    if prefix in CHAPTER_PREFIXES:
        for ch in data.get("chapters") or []:
            if isinstance(ch, dict) and str(ch.get("title") or "")[:2] == prefix:
                return {"chapters": [ch]}
        raise HTTPException(status_code=502, detail=f"AI 未返回「{section}」，请重新生成")
    raise HTTPException(status_code=400, detail=f"无效分节：{section}")


def _next_plan_version(db: Session, subject_id: int) -> int:
    latest = db.query(CoursePlan).filter(
        CoursePlan.subject_id == subject_id
    ).order_by(CoursePlan.version.desc()).first()
    return (latest.version + 1) if latest else 1


def _create_course_plan(db: Session, subject_id: int, plan_rows: list) -> Optional[CoursePlan]:
    """从 plan 数组创建新规划版本（归档旧 active）；无 plan 行返回 None"""
    if not plan_rows:
        return None
    # 归档旧 active 规划
    for old in db.query(CoursePlan).filter(
            CoursePlan.subject_id == subject_id,
            CoursePlan.status == "active",
    ).all():
        old.status = "archived"
    plan = CoursePlan(
        subject_id=subject_id,
        version=_next_plan_version(db, subject_id),
        plan_json=_dump(plan_rows),
        status="active",
        created_at=now_iso(),
    )
    db.add(plan)
    db.flush()  # 拿 id 供 report.course_plan_id 关联
    return plan


# ---------------------------------------------------------------- 主流程

def generate_report(db: Session, subject_id: int, data: dict = None) -> dict:
    """生成学习计划：基于最近 completed 会话总结 + 学生/学科信息，AI 生成章式计划 + 课程规划"""
    data = data or {}
    subject = _get_subject(db, subject_id)
    student = db.get(Student, subject.student_id)
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")

    conv_id = data.get("conversation_id")
    summary = _conversation_summary(db, subject_id, conv_id)
    kb_context, kb_refs = _retrieve_kb_context(
        db, f"学生{student.name} 学科{subject.name} 学习计划")

    prompt = render_prompt(
        "report_generation.txt",
        student_name=student.name,
        subject_name=subject.name,
        student_info=_build_student_info(student),
        conversation_summary=summary,
        kb_context=kb_context,  # StrictUndefined：未就绪也必须传空串
    )
    text = _call_llm(prompt)
    parsed = _parse_report_output(text)

    # 关联会话：优先 body 指定的，否则取最近 completed（无则 None）
    resolved_conv_id = None
    if conv_id:
        conv = db.get(AIConversation, conv_id)
        if conv and conv.subject_id == subject_id:
            resolved_conv_id = conv_id
    else:
        conv = db.query(AIConversation).filter(
            AIConversation.subject_id == subject_id,
            AIConversation.status == "completed",
        ).order_by(AIConversation.updated_at.desc()).first()
        resolved_conv_id = conv.id if conv else None

    plan = _create_course_plan(db, subject_id, parsed["plan"])
    report = Report(
        subject_id=subject_id,
        conversation_id=resolved_conv_id,
        title=parsed["title"] or f"{student.name}-{subject.name} 冲刺学习计划",
        content_json=_dump(parsed),
        course_plan_id=plan.id if plan else None,
        kb_references_json=_dump(parsed["kb_references"]),
        status="draft",
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report.to_dict()


def regenerate_report(db: Session, report_id: int, data: dict = None) -> dict:
    """重新生成计划：{extra_info, section?}；section 缺省全量，否则只重生成该章/summary/plan/conclusion"""
    data = data or {}
    report = _get_report(db, report_id)
    extra_info = str(data.get("extra_info") or "").strip()
    section = str(data.get("section") or "").strip()
    if section and section not in REGEN_KEYS and section[:2] not in CHAPTER_PREFIXES:
        raise HTTPException(status_code=400, detail=f"无效分节：{section}")

    original = _load_json(report.content_json, {})
    if not isinstance(original.get("chapters"), list):
        # 旧版 4 节结构：不支持章节级重生成，强制全量
        if section:
            raise HTTPException(status_code=400, detail="旧版报告，请先重新生成整份报告")
        original = {}

    prompt = render_prompt(
        "report_regenerate.txt",
        original_content=_dump(original),
        extra_info=extra_info,  # StrictUndefined：缺省传空串
        section=section,
    )
    text = _call_llm(prompt)
    parsed = _parse_regenerate_output(text, section)

    if section:
        if section == "summary":
            original["summary"] = parsed["summary"]
        elif section == "conclusion":
            original["conclusion"] = parsed["conclusion"]
        elif section == "plan":
            plan_rows = parsed["plan"]
            original["plan"] = plan_rows
            plan = _create_course_plan(db, report.subject_id, plan_rows)
            if plan:
                report.course_plan_id = plan.id
        else:  # 章节前缀
            new_ch = _parse_chapter(parsed["chapters"][0])
            prefix = section[:2]
            chapters = original.get("chapters") or []
            replaced = False
            for i, ch in enumerate(chapters):
                if isinstance(ch, dict) and str(ch.get("title") or "")[:2] == prefix:
                    chapters[i] = new_ch
                    replaced = True
                    break
            if not replaced:
                chapters.append(new_ch)
            original["chapters"] = chapters
        content_json = original
    else:
        parsed_full = _parse_report_output(text)
        plan = _create_course_plan(db, report.subject_id, parsed_full["plan"])
        if plan:
            report.course_plan_id = plan.id
        if parsed_full.get("kb_references"):
            report.kb_references_json = _dump(parsed_full["kb_references"])
        report.title = parsed_full["title"] or report.title
        content_json = parsed_full

    report.content_json = _dump(content_json)
    report.updated_at = now_iso()
    db.commit()
    db.refresh(report)
    return report.to_dict()
