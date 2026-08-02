"""
P4 AI 对话式采集 — 对话业务逻辑

设计要点：
- messages_json 存 [{role: 'ai'|'user', content, time}, ...]（role 用 ai/user，与需求文档一致）
- 每轮 1 次 LLM 调用：conversation.txt 要求输出 JSON {"reply", "enough"}
  - 信息不足 → reply 为下一个问题，enough=false
  - 信息足够 → reply 为收尾语，enough=true（should_end 信号，不改 status，用户可补充或手动结束）
- 结束（自动 should_end 后点结束 / 手动提前结束）统一走 end_conversation：
  conversation_end.txt 生成学情总结，追加为最后一条 AI 消息，status 置 completed
- 对话环节不查知识库（RAG ❌，仅用于 P5 报告 / P8 问答）
"""
import json
import re

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.ai.manager import ai_manager
from backend.ai.prompts.prompt_loader import render_prompt
from backend.models.ai_conversation import AIConversation
from backend.models.student import Student
from backend.models.subject import Subject
from backend.utils.helpers import now_iso

# 对话追问用较低温度保证提问稳定；总结用更低温度保证事实性
DIALOGUE_TEMPERATURE = 0.4
SUMMARY_TEMPERATURE = 0.3
# 学情总结追加为 AI 消息时的固定前缀（展示用），返回给前端时统一剥掉保持 summary 字段一致
SUMMARY_PREFIX = "【学情总结】\n"


# ---------------------------------------------------------------- 私有工具

def _get_subject(db: Session, subject_id: int) -> Subject:
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="学科不存在")
    return subject


def _get_conversation(db: Session, subject_id: int, conversation_id: int) -> AIConversation:
    """获取会话并校验归属（防止跨学科操作）"""
    conv = db.get(AIConversation, conversation_id)
    if not conv or conv.subject_id != subject_id:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conv


def _load_messages(conv: AIConversation) -> list:
    """解析 messages_json，容错返回 []"""
    try:
        data = json.loads(conv.messages_json or "[]")
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _save(db: Session, conv: AIConversation, msgs: list):
    conv.messages_json = json.dumps(msgs, ensure_ascii=False)
    conv.updated_at = now_iso()
    db.commit()
    db.refresh(conv)


def _append(db: Session, conv: AIConversation, role: str, content: str) -> list:
    """追加一条消息并保存，返回最新消息数组"""
    msgs = _load_messages(conv)
    msgs.append({"role": role, "content": content, "time": now_iso()})
    _save(db, conv, msgs)
    return msgs


def _display_history(msgs: list) -> list:
    """把 ai/user 角色映射为 assistant/user，供 Jinja2 模板渲染对话历史"""
    result = []
    for m in msgs:
        role = m.get("role", "")
        mapped = "assistant" if role in ("ai", "assistant") else "user"
        result.append({"role": mapped, "content": m.get("content", "")})
    return result


def _subjects_info(db: Session, subject: Subject) -> str:
    """该学生其他活跃学科名（逗号分隔），用于让 AI 只围绕当前学科提问"""
    others = db.query(Subject).filter(
        Subject.student_id == subject.student_id,
        Subject.id != subject.id,
        Subject.status == "active",
    ).all()
    names = [s.name for s in others]
    return "、".join(names) if names else "无"


def _extract_json(text: str):
    """从 LLM 输出中稳健提取 JSON 对象：
    1. 剥 ```json 围栏；2. 截取首个 { 到末尾 } 之间的子串；3. json.loads
    解析失败返回 None（由调用方降级处理）
    """
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def _parse_reply(text: str):
    """解析对话回复，返回 (reply, enough)；失败时整段输出当 reply、enough=False"""
    data = _extract_json(text)
    if isinstance(data, dict) and data.get("reply"):
        reply = str(data["reply"]).strip()
        enough = data.get("enough", False)
        if isinstance(enough, str):
            enough = enough.strip().lower() in ("true", "yes", "1")
        else:
            enough = bool(enough)
        return reply, enough
    return (text or "").strip(), False


def _call_llm(messages: list, temperature: float) -> str:
    """统一 LLM 调用入口：未配置抛 503，调用失败抛 502"""
    llm = ai_manager.get_llm()
    if not llm:
        raise HTTPException(status_code=503, detail="AI 服务未配置，请先在系统设置中配置 LLM")
    try:
        return llm.chat(messages, temperature=temperature) or ""
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 调用失败：{e}")


def _run_turn(db: Session, conv: AIConversation, subject: Subject, student: Student, msgs: list):
    """一轮对话：渲染 conversation.txt + system_prompt.txt，返回 (reply, enough)"""
    system = render_prompt("system_prompt.txt")
    prompt = render_prompt(
        "conversation.txt",
        student_name=student.name,
        subject_name=subject.name,
        history=_display_history(msgs),
        subjects_info=_subjects_info(db, subject),
    )
    reply, enough = _parse_reply(_call_llm([
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ], temperature=DIALOGUE_TEMPERATURE))
    return reply, enough


def conversation_to_dict(conv: AIConversation, msgs: list = None) -> dict:
    """会话 dict（messages 为解析后的数组，不是 JSON 字符串）"""
    if msgs is None:
        msgs = _load_messages(conv)
    return {
        "id": conv.id,
        "subject_id": conv.subject_id,
        "messages": msgs,
        "status": conv.status,
        "created_at": conv.created_at,
        "updated_at": conv.updated_at,
    }


# ---------------------------------------------------------------- 对外接口

def start_conversation(db: Session, subject_id: int) -> dict:
    """开始（或恢复）一次 AI 对话采集。

    幂等：该学科存在 in_progress 会话则直接复用（页面刷新不重复建会话）；
    否则创建新会话。已配置 LLM 且会话为空时，自动生成第一条 AI 问题（F4.1）。
    首问失败或未配置时留空会话返回，前端可重试或引导去设置页。
    """
    subject = _get_subject(db, subject_id)
    student = db.get(Student, subject.student_id)

    conv = db.query(AIConversation).filter(
        AIConversation.subject_id == subject_id,
        AIConversation.status == "in_progress",
    ).order_by(AIConversation.updated_at.desc()).first()
    if not conv:
        conv = AIConversation(subject_id=subject_id, messages_json="[]", status="in_progress")
        db.add(conv)
        db.commit()
        db.refresh(conv)

    configured = ai_manager.is_configured("llm")
    msgs = _load_messages(conv)
    first_question_failed = False
    # 空会话 + 已配置 → 补首个问题（覆盖"先未配置后配置"的恢复路径）
    if configured and not msgs:
        try:
            reply, _ = _run_turn(db, conv, subject, student, msgs)
            if reply:
                msgs = _append(db, conv, "ai", reply)
            else:
                first_question_failed = True
        except Exception:
            first_question_failed = True  # 首问失败留空，前端可提示重试（重调 start 幂等安全）

    return {
        "conversation": conversation_to_dict(conv, msgs),
        "configured": configured,
        "first_question_failed": first_question_failed,
        "subject_name": subject.name,
        "student_name": student.name,
    }


def handle_message(db: Session, subject_id: int, conversation_id: int, message_text: str) -> dict:
    """处理一条教务消息：追加用户消息 → AI 回复 → 返回 (reply, should_end)

    - should_end=True 仅是"AI 认为信息已足够"的信号（收尾语已作为 reply），
      不改变 status；用户可继续补充或点结束（F4.4 / F4.5）
    - summary 统一在 end_conversation 生成（F4.6）
    """
    subject = _get_subject(db, subject_id)
    student = db.get(Student, subject.student_id)
    conv = _get_conversation(db, subject_id, conversation_id)
    if conv.status != "in_progress":
        raise HTTPException(status_code=400, detail="对话已结束，如需再次采集请重新建档对话")
    text = (message_text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="消息内容不能为空")

    msgs = _append(db, conv, "user", text)

    if not ai_manager.is_configured("llm"):
        hint = "AI 服务未配置，请先在「系统设置」中配置 LLM 后再继续对话。"
        msgs = _append(db, conv, "ai", hint)
        return {
            "conversation_id": conv.id,
            "reply": hint,
            "should_end": False,
            "summary": None,
            "messages": msgs,
            "status": conv.status,
        }

    try:
        reply, enough = _run_turn(db, conv, subject, student, msgs)
        if not reply:
            reply = "抱歉，我没有理解你的回答，可以再说一下吗？"
        msgs = _append(db, conv, "ai", reply)
        return {
            "conversation_id": conv.id,
            "reply": reply,
            "should_end": enough,
            "summary": None,
            "messages": msgs,
            "status": conv.status,
        }
    except Exception:
        # LLM 异常 → 追加友好提示气泡，不崩会话
        reply = "抱歉，AI 服务暂时不可用，请稍后再试。"
        msgs = _append(db, conv, "ai", reply)
        return {
            "conversation_id": conv.id,
            "reply": reply,
            "should_end": False,
            "summary": None,
            "messages": msgs,
            "status": conv.status,
        }


def end_conversation(db: Session, subject_id: int, conversation_id: int) -> dict:
    """结束对话（手动提前结束 / should_end 后点结束）：生成学情总结，置 completed

    幂等：已 completed 时返回最后一条 AI 消息内容作为总结。
    """
    subject = _get_subject(db, subject_id)
    student = db.get(Student, subject.student_id)
    conv = _get_conversation(db, subject_id, conversation_id)
    msgs = _load_messages(conv)

    if conv.status == "completed":
        summary = ""
        for m in reversed(msgs):
            if m.get("role") == "ai":
                raw = m.get("content", "")
                # 剥掉存储时的展示前缀，保证 summary 与首次 end 返回的纯文本一致
                summary = raw[len(SUMMARY_PREFIX):] if raw.startswith(SUMMARY_PREFIX) else raw
                break
        return {
            "conversation_id": conv.id,
            "summary": summary,
            "report_id": None,
            "messages": msgs,
            "status": "completed",
        }

    summary = None
    if ai_manager.is_configured("llm"):
        try:
            system = render_prompt("system_prompt.txt")
            summary = _call_llm([
                {"role": "system", "content": system},
                {"role": "user", "content": render_prompt(
                    "conversation_end.txt",
                    student_name=student.name,
                    subject_name=subject.name,
                    history=_display_history(msgs),
                )},
            ], temperature=SUMMARY_TEMPERATURE).strip()
        except Exception:
            summary = None
    if not summary:
        summary = "对话已结束。学情总结生成失败，可稍后重新对话采集。"

    msgs = _append(db, conv, "ai", SUMMARY_PREFIX + summary)
    conv.status = "completed"
    conv.updated_at = now_iso()
    db.commit()
    db.refresh(conv)

    return {
        "conversation_id": conv.id,
        "summary": summary,
        "report_id": None,  # P5 生成完整报告时再关联
        "messages": msgs,
        "status": "completed",
    }
