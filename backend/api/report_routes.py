"""
Report API Routes.

Endpoints for generating, checking status, downloading,
listing, and deleting reports.
"""

import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from schemas.report_schema import (
    ReportRequest, ReportResponse, ReportStatus, ReportFormat,
)
from services.report_service import get_report_service
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/reports", tags=["Reports"])


@router.post("/generate", response_model=ReportResponse)
async def generate_report(request: ReportRequest):
    """Generate a report from RAG query results.

    Accepts the query, answer, sources, and options.
    Returns report metadata with a download URL once ready.
    """
    service = get_report_service()

    logger.info(
        "Report generation requested",
        format=request.report_type.value,
        title=request.title,
        query_length=len(request.query),
    )

    response = await service.generate(request)

    if response.status == ReportStatus.ERROR:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {response.error}")

    return response


@router.get("/{report_id}/status", response_model=ReportResponse)
async def get_report_status(report_id: str):
    """Check the status of a report generation job."""
    service = get_report_service()
    report = service.get_report(report_id)

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    return report


@router.get("/{report_id}/download")
async def download_report(report_id: str):
    """Download a generated report file."""
    service = get_report_service()
    report = service.get_report(report_id)

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if report.status != ReportStatus.READY:
        raise HTTPException(status_code=400, detail=f"Report is not ready. Status: {report.status.value}")

    file_path = service.get_report_file_path(report_id)
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Report file not found on disk")

    # Determine media type
    media_types = {
        ReportFormat.PDF: "application/pdf",
        ReportFormat.EXCEL: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ReportFormat.WORD: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ReportFormat.CSV: "text/csv",
        ReportFormat.CHART: "image/png",
    }

    media_type = media_types.get(report.format, "application/octet-stream")

    return FileResponse(
        path=file_path,
        filename=report.filename,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{report.filename}"'},
    )


@router.get("/", response_model=list[ReportResponse])
async def list_reports():
    """List all generated reports."""
    service = get_report_service()
    return service.list_reports()


@router.delete("/{report_id}")
async def delete_report(report_id: str):
    """Delete a generated report."""
    service = get_report_service()

    if not service.get_report(report_id):
        raise HTTPException(status_code=404, detail="Report not found")

    service.delete_report(report_id)
    return {"message": "Report deleted", "report_id": report_id}
