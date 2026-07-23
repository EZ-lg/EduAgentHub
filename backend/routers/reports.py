"""
报告 API（P5 实现完整逻辑）
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.models import get_db
from backend.models.report import Report
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
    """生成报告（P5 实现 AI 生成逻辑）"""
    return success_response({"info": "报告生成功能将在 P5 实现"})


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
    report.updated_at = now_iso()
    db.commit()
    db.refresh(report)
    return success_response(report.to_dict())


@router.post("/reports/{report_id}/regenerate")
def regenerate_report(report_id: int, data: dict = None, db: Session = Depends(get_db)):
    """重新生成报告（P5 实现）"""
    return success_response({"info": "重新生成功能将在 P5 实现"})


@router.get("/reports/{report_id}/pdf")
def export_pdf(report_id: int, db: Session = Depends(get_db)):
    """导出 PDF（P5 实现）"""
    return success_response({"info": "PDF 导出将在 P5 实现"})
