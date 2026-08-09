"""
报告 API（P5：生成 / 重新生成 / PDF 数据装配 / docx 导出）
"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from backend.models import get_db
from backend.models.report import Report
from backend.models.setting import Setting
from backend.models.student import Student
from backend.models.subject import Subject
from backend.services import report_generator
from backend.utils.activity import log_activity
from backend.utils.export_docx import build_report_docx
from backend.utils.helpers import success_response, now_iso

router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/subjects/{subject_id}/reports")
def list_reports(subject_id: int, db: Session = Depends(get_db)):
    """报告列表"""
    reports = db.query(Report).filter(
        Report.subject_id == subject_id
    ).order_by(Report.created_at.desc()).all()
    return success_response([r.to_dict() for r in reports])


@router.post("/subjects/{subject_id}/reports/generate")
def generate_report(subject_id: int, data: dict = None, db: Session = Depends(get_db)):
    """生成报告：基于最近 completed 会话的学情总结，AI 生成 4 节 + 课程规划记录"""
    report = report_generator.generate_report(db, subject_id, data or {})
    log_activity(db, "生成学情报告", f"报告「{report.get('title') or ''}」", subject_id=subject_id)
    db.commit()
    return success_response(report)


@router.get("/reports/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db)):
    """报告详情"""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    return success_response(report.to_dict())


@router.put("/reports/{report_id}")
def update_report(report_id: int, data: dict, db: Session = Depends(get_db)):
    """编辑报告"""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    if "title" in data:
        report.title = data["title"]
    if "content_json" in data:
        report.content_json = data["content_json"]
    if "status" in data:
        report.status = data["status"]
    if "course_plan_id" in data:
        # 指向最新课程规划版本（P6：报告页/规划Tab保存新版本后同步）
        report.course_plan_id = data["course_plan_id"] if data["course_plan_id"] is not None else None
    report.updated_at = now_iso()
    log_activity(db, "编辑报告", f"报告「{report.title}」", subject_id=report.subject_id)
    db.commit()
    db.refresh(report)
    return success_response(report.to_dict())


@router.post("/reports/{report_id}/regenerate")
def regenerate_report(report_id: int, data: dict = None, db: Session = Depends(get_db)):
    """重新生成报告：body {extra_info, section?}，section 缺省全量重生成"""
    report = report_generator.regenerate_report(db, report_id, data or {})
    log_activity(db, "重新生成报告", f"报告「{report.get('title') or ''}」", subject_id=report.get("subject_id"))
    db.commit()
    return success_response(report)


@router.delete("/reports/{report_id}")
def delete_report(report_id: int, db: Session = Depends(get_db)):
    """删除报告。course_plan 为独立版本化实体，不级联删除（删报告不影响规划版本历史）"""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    log_activity(db, "删除报告", f"报告「{report.title}」", subject_id=report.subject_id)
    db.delete(report)
    db.commit()
    return success_response({"deleted": True})


@router.get("/reports/{report_id}/pdf")
def export_pdf(report_id: int, db: Session = Depends(get_db)):
    """导出数据装配：报告 + 学科 + 学生 + 机构名（PDF 由前端 jsPDF + html2canvas 渲染）"""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    subject = db.get(Subject, report.subject_id)
    student = db.get(Student, subject.student_id) if subject else None
    org = db.query(Setting).filter(Setting.key == "org_name").first()
    org_name = ""
    org_info = None
    if org and org.value_json:
        try:
            import json
            parsed = json.loads(org.value_json)
            if isinstance(parsed, dict):
                org_info = parsed
                org_name = str(parsed.get("name") or "")
        except Exception:
            org_name = ""
    return success_response({
        "report": report.to_dict(),
        "subject": subject.to_dict() if subject else None,
        "student": student.to_dict() if student else None,
        "org_name": org_name,
        "org_info": org_info,
    })


@router.post("/reports/{report_id}/docx")
def export_docx(report_id: int, data: dict = None, db: Session = Depends(get_db)):
    """导出 Word（docx）：按机构模板排版生成单科学习计划，浏览器下载

    body 可选：{content_json: "..."} —— 前端把当前编辑后的 content_json 传过来，
    确保导出的 Word 始终是「编辑过后」的内容（即使未点保存规划）；
    未传则回退到 DB 最后保存的 content_json。
    """
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    subject = db.get(Subject, report.subject_id)
    student = db.get(Student, subject.student_id) if subject else None
    org = db.query(Setting).filter(Setting.key == "org_name").first()
    org_name = ""
    if org and org.value_json:
        try:
            import json as _json
            parsed = _json.loads(org.value_json)
            if isinstance(parsed, dict):
                org_name = str(parsed.get("name") or "")
        except Exception:
            org_name = ""
    buf = build_report_docx(report, subject, student, org_name=org_name, content_json_override=(data or {}).get("content_json"))
    fname = f"{student.name if student else '学生'}-{subject.name if subject else ''}-冲刺学习计划.docx"
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"},
    )
