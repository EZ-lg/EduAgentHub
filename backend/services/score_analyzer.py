"""
P6 成绩分析 + 课程规划调整 — 业务逻辑

数据流：
- analyze_scores：学科成绩数组 → score_analysis.txt → LLM → 结构化分析 JSON
  （趋势 / 薄弱点 / 与目标差距 / 建议 / 目标百分比），供前端展示 + 画目标参考线
- adjust_plan_preview：成绩分析 + 当前 active 规划 → plan_adjustment.txt → LLM → 调整建议
  （proposed_plan + reason）。**只预览不落库**，由前端「保存为新版本」时落库
- save_plan_version：手动保存规划新版本（归档旧 active，写 adjustment_reason）

设计要点：
- 复用 report_generator 的私有工具（_get_subject/_call_llm/_retrieve_kb_context/
  _create_course_plan/_parse_plan/_load_json/_dump），保持 P8 RAG 接入点唯一
- RAG 优雅降级：embedding 未配置 / 无 active 知识文档 → kb_context 传空串
- 课程规划版本纪律：每次变更（含回退/AI调整保存）新建 CoursePlan 版本并归档旧 active
"""
import json
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.ai.manager import ai_manager
from backend.ai.prompts.prompt_loader import render_prompt
from backend.models.course_plan import CoursePlan
from backend.models.report import Report
from backend.models.score import Score
from backend.models.student import Student
from backend.models.subject import Subject
from backend.services import report_generator
from backend.services.conversation_service import _extract_json
from backend.utils.helpers import now_iso

SCORE_ANALYSIS_TEMPERATURE = 0.3
PLAN_ADJUST_TEMPERATURE = 0.3
GOAL_CHAPTER_PREFIX = "一、"


def _get_subject(db: Session, subject_id: int) -> Subject:
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="学科不存在")
    return subject


def _load_scores(db: Session, subject_id: int) -> list:
    """读该学科全部成绩，按考试日期升序（供 LLM 看时间线）"""
    return db.query(Score).filter(
        Score.subject_id == subject_id
    ).order_by(Score.exam_date.asc()).all()


def _pct(score: float, total: float) -> str:
    if not total or total <= 0:
        return "-"
    return f"{score / total * 100:.1f}%"


def _format_scores(scores: list) -> str:
    """成绩 → 紧凑文本：序号. 日期 | 考试 | 原始分/满分 | 百分制"""
    if not scores:
        return "（暂无成绩记录）"
    lines = []
    for i, s in enumerate(scores, 1):
        lines.append(
            f"{i}. {s.exam_date} | {s.exam_name or '未命名考试'} | "
            f"{s.score}/{s.total_score} ({_pct(s.score, s.total_score)})"
        )
    return "\n".join(lines)


def _goal_context(db: Session, subject_id: int) -> str:
    """从最新报告的「一、当前情况与目标」章提取目标/现状上下文；逐级降级为占位串"""
    report = db.query(Report).filter(
        Report.subject_id == subject_id
    ).order_by(Report.created_at.desc()).first()
    if not report:
        return "（暂无报告，目标信息缺失）"
    data = report_generator._load_json(report.content_json, {})
    for ch in data.get("chapters") or []:
        if isinstance(ch, dict) and str(ch.get("title") or "")[:2] == GOAL_CHAPTER_PREFIX:
            content = str(ch.get("content") or "").strip()
            return content or "（报告未填写目标信息）"
    return "（报告未包含「当前情况与目标」章节）"


def _parse_analysis(text: str) -> dict:
    """解析成绩分析输出 → 结构化 dict；失败抛 502"""
    data = _extract_json(text)
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="AI 返回格式不正确，请重新分析")

    trend = str(data.get("trend") or "")
    allowed = ("上升", "下降", "波动", "平稳", "上升后回落")
    if trend not in allowed:
        trend = "波动"

    weak_points = data.get("weak_points")
    if isinstance(weak_points, list):
        cleaned = []
        for wp in weak_points[:5]:
            if isinstance(wp, dict):
                cleaned.append({
                    "area": str(wp.get("area") or ""),
                    "detail": str(wp.get("detail") or ""),
                })
            elif isinstance(wp, str) and wp.strip():
                cleaned.append({"area": wp.strip(), "detail": ""})
        weak_points = cleaned
    else:
        weak_points = []

    suggestions = data.get("suggestions")
    if isinstance(suggestions, list):
        suggestions = [str(x).strip() for x in suggestions[:6] if str(x).strip()]
    else:
        suggestions = []

    # 目标百分比：整数 0-100 或 None（前端画参考线用）
    goal_percent = None
    gp = data.get("goal_percent")
    if gp not in (None, "", "null"):
        try:
            gp_val = int(float(gp))
            if 0 <= gp_val <= 100:
                goal_percent = gp_val
        except (TypeError, ValueError):
            goal_percent = None

    return {
        "trend": trend,
        "trend_detail": str(data.get("trend_detail") or "").strip(),
        "weak_points": weak_points,
        "gap_analysis": str(data.get("gap_analysis") or "").strip(),
        "suggestions": suggestions,
        "goal_percent": goal_percent,
    }


def _analysis_to_text(a: dict) -> str:
    """分析 dict → 紧凑文本（供 plan_adjustment 的 score_analysis 变量）"""
    parts = [f"趋势：{a['trend']}"]
    if a.get("trend_detail"):
        parts.append(f"趋势详情：{a['trend_detail']}")
    if a.get("weak_points"):
        wps = "；".join(
            f"{w.get('area') or '未标注'}" + (f"（{w.get('detail')}）" if w.get("detail") else "")
            for w in a["weak_points"]
        )
        parts.append(f"薄弱点：{wps}")
    if a.get("gap_analysis"):
        parts.append(f"与目标差距：{a['gap_analysis']}")
    if a.get("suggestions"):
        parts.append("建议：" + "；".join(a["suggestions"]))
    return "\n".join(parts)


def _active_plan(db: Session, subject_id: int) -> Optional[CoursePlan]:
    """最新 active 规划；无 active 则取最新一条（含归档）"""
    plan = db.query(CoursePlan).filter(
        CoursePlan.subject_id == subject_id,
        CoursePlan.status == "active",
    ).order_by(CoursePlan.version.desc()).first()
    if plan:
        return plan
    return db.query(CoursePlan).filter(
        CoursePlan.subject_id == subject_id,
    ).order_by(CoursePlan.version.desc()).first()


# ---------------------------------------------------------------- 主流程

def analyze_scores(db: Session, subject_id: int) -> dict:
    """AI 成绩分析：基于该学科历次成绩 + 目标上下文，返回结构化分析"""
    subject = _get_subject(db, subject_id)
    student = db.get(Student, subject.student_id)
    scores = _load_scores(db, subject_id)
    if not scores:
        raise HTTPException(status_code=400, detail="暂无成绩数据，请先录入成绩")

    kb_context, _ = report_generator._retrieve_kb_context(
        db, f"学生{student.name if student else ''} 学科{subject.name} 成绩分析")

    prompt = render_prompt(
        "score_analysis.txt",
        student_name=student.name if student else "该生",
        subject_name=subject.name,
        scores=_format_scores(scores),
        goal_context=_goal_context(db, subject_id),
        kb_context=kb_context,  # StrictUndefined：未就绪也必须传空串
    )
    text = report_generator._call_llm(prompt, SCORE_ANALYSIS_TEMPERATURE)
    analysis = _parse_analysis(text)

    return {
        "analysis": analysis,
        "subject_name": subject.name,
        "student_name": student.name if student else "",
        "score_count": len(scores),
    }


def adjust_plan_preview(db: Session, subject_id: int) -> dict:
    """AI 课程调整建议（预览，不落库）：成绩分析 + 当前规划 → 调整后规划 + 原因"""
    subject = _get_subject(db, subject_id)
    student = db.get(Student, subject.student_id)

    # 成绩分析（内部会校验有成绩，无则抛 400）
    result = analyze_scores(db, subject_id)
    analysis = result["analysis"]

    plan = _active_plan(db, subject_id)
    if not plan:
        raise HTTPException(status_code=400, detail="暂无课程规划，请先生成报告")
    try:
        current_rows = json.loads(plan.plan_json or "[]")
        if not isinstance(current_rows, list):
            current_rows = []
    except (json.JSONDecodeError, TypeError):
        current_rows = []

    kb_context, _ = report_generator._retrieve_kb_context(
        db, f"学生{student.name if student else ''} 学科{subject.name} 课程规划调整")

    prompt = render_prompt(
        "plan_adjustment.txt",
        student_name=student.name if student else "该生",
        subject_name=subject.name,
        current_plan=json.dumps(current_rows, ensure_ascii=False),
        score_analysis=_analysis_to_text(analysis),
        kb_context=kb_context,
    )
    text = report_generator._call_llm(prompt, PLAN_ADJUST_TEMPERATURE)
    data = _extract_json(text)
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="AI 返回格式不正确，请重新调整")

    reason = str(data.get("reason") or "").strip()
    plan_rows = report_generator._parse_plan(data.get("plan"))

    return {
        "analysis": analysis,
        "proposed_plan": plan_rows,
        "reason": reason,
        "source_version": plan.version,
    }


def save_plan_version(db: Session, subject_id: int, plan_rows: list, adjustment_reason: str = "") -> dict:
    """手动保存课程规划新版本（归档旧 active）；返回新规划"""
    _get_subject(db, subject_id)
    if not plan_rows:
        raise HTTPException(status_code=400, detail="课程规划不能为空")
    plan = report_generator._create_course_plan(
        db, subject_id, report_generator._parse_plan(plan_rows), adjustment_reason=adjustment_reason)
    if not plan:
        raise HTTPException(status_code=400, detail="课程规划不能为空")
    db.commit()
    db.refresh(plan)
    return plan.to_dict()
