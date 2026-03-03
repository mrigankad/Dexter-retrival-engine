"""
Report Service — Orchestrates report generation.

Coordinates ChartEngine, DataEngine, and document builders
to produce professional reports from RAG query outputs.
"""

import os
import uuid
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional

from src.core.logger import get_logger
from schemas.report_schema import (
    ReportRequest, ReportResponse, ReportFormat,
    ReportStatus, SourceChunk,
)
from reports.chart_engine import ChartEngine
from reports.data_engine import DataEngine

logger = get_logger(__name__)

# ── Storage Directory ────────────────────────────────────────
REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "generated_reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


class ReportService:
    """Orchestrates report generation across all formats."""

    def __init__(self):
        self.chart_engine = ChartEngine()
        self.data_engine = DataEngine()
        self._reports: Dict[str, ReportResponse] = {}

    async def generate(self, request: ReportRequest) -> ReportResponse:
        """Generate a report based on the request format.

        Returns ReportResponse with download path.
        """
        report_id = str(uuid.uuid4())

        response = ReportResponse(
            report_id=report_id,
            status=ReportStatus.PROCESSING,
            format=request.report_type,
            created_at=datetime.now(),
        )
        self._reports[report_id] = response

        try:
            # Extract structured data
            kpis = self.data_engine.extract_kpis(request.answer)
            tables = self.data_engine.extract_tables(request.answer)

            # Convert sources to dicts
            sources = [s.model_dump() for s in request.sources] if request.sources else []

            # Generate charts if requested
            charts = []
            if request.options.include_charts:
                charts = await asyncio.get_event_loop().run_in_executor(
                    None,
                    self.chart_engine.generate_all_charts,
                    request.answer,
                    sources,
                )
                logger.info(f"Generated {len(charts)} charts for report {report_id}")

            # Build the document
            if request.report_type == ReportFormat.PDF:
                doc_bytes, filename = await self._build_pdf(request, charts, kpis, tables, sources)
            elif request.report_type == ReportFormat.EXCEL:
                doc_bytes, filename = await self._build_excel(request, kpis, tables, sources)
            elif request.report_type == ReportFormat.WORD:
                doc_bytes, filename = await self._build_word(request, charts, kpis, sources)
            elif request.report_type == ReportFormat.CSV:
                doc_bytes, filename = await self._build_csv(request, tables, sources)
            elif request.report_type == ReportFormat.CHART:
                doc_bytes, filename = await self._build_chart_only(request, charts)
            else:
                raise ValueError(f"Unsupported format: {request.report_type}")

            # Save to disk
            output_path = os.path.join(REPORTS_DIR, filename)
            with open(output_path, "wb") as f:
                f.write(doc_bytes)

            file_size = len(doc_bytes) / 1024  # KB

            response.status = ReportStatus.READY
            response.filename = filename
            response.download_url = f"/api/reports/{report_id}/download"
            response.progress = 100
            response.file_size_kb = round(file_size, 1)

            logger.info(
                "Report generated successfully",
                report_id=report_id,
                format=request.report_type.value,
                filename=filename,
                size_kb=round(file_size, 1),
            )

        except Exception as e:
            response.status = ReportStatus.ERROR
            response.error = str(e)
            logger.error(f"Report generation failed: {e}", report_id=report_id)

        self._reports[report_id] = response
        return response

    def get_report(self, report_id: str) -> Optional[ReportResponse]:
        """Get report status/metadata."""
        return self._reports.get(report_id)

    def get_report_file_path(self, report_id: str) -> Optional[str]:
        """Get the file path for a completed report."""
        report = self._reports.get(report_id)
        if report and report.status == ReportStatus.READY and report.filename:
            path = os.path.join(REPORTS_DIR, report.filename)
            if os.path.exists(path):
                return path
        return None

    def list_reports(self) -> List[ReportResponse]:
        """List all generated reports."""
        return list(self._reports.values())

    def delete_report(self, report_id: str) -> bool:
        """Delete a report and its file."""
        report = self._reports.get(report_id)
        if not report:
            return False

        if report.filename:
            path = os.path.join(REPORTS_DIR, report.filename)
            if os.path.exists(path):
                os.remove(path)

        del self._reports[report_id]
        return True

    # ── Build Methods ────────────────────────────────────────

    async def _build_pdf(self, req, charts, kpis, tables, sources):
        from reports.pdf_builder import generate_pdf_report
        import pandas as pd

        def _build():
            return generate_pdf_report(
                query=req.query,
                answer=req.answer,
                sources=sources if req.options.include_sources else None,
                charts=charts,
                kpis=kpis if kpis else None,
                title=req.title,
            )

        doc_bytes = await asyncio.get_event_loop().run_in_executor(None, _build)
        filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        return doc_bytes, filename

    async def _build_excel(self, req, kpis, tables, sources):
        from reports.excel_builder import generate_excel_report
        import pandas as pd

        dataframes = {}
        for i, df in enumerate(tables):
            dataframes[f"Data {i+1}"] = df

        # Also add sources as a DataFrame
        if sources and req.options.include_sources:
            src_df = self.data_engine.sources_to_dataframe(sources)
            dataframes["Sources"] = src_df

        def _build():
            return generate_excel_report(
                query=req.query,
                answer=req.answer,
                sources=sources if req.options.include_sources else None,
                kpis=kpis if kpis else None,
                dataframes=dataframes if dataframes else None,
                title=req.title,
            )

        doc_bytes = await asyncio.get_event_loop().run_in_executor(None, _build)
        filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return doc_bytes, filename

    async def _build_word(self, req, charts, kpis, sources):
        from reports.word_builder import generate_word_report

        def _build():
            return generate_word_report(
                query=req.query,
                answer=req.answer,
                sources=sources if req.options.include_sources else None,
                charts=charts,
                kpis=kpis if kpis else None,
                title=req.title,
            )

        doc_bytes = await asyncio.get_event_loop().run_in_executor(None, _build)
        filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        return doc_bytes, filename

    async def _build_csv(self, req, tables, sources):
        import pandas as pd

        if tables:
            df = tables[0]
        elif sources:
            df = self.data_engine.sources_to_dataframe(sources)
        else:
            # Fallback: answer lines as data
            lines = [l.strip() for l in req.answer.split("\n") if l.strip()]
            df = pd.DataFrame({"Content": lines})

        csv_bytes = self.data_engine.to_csv(df)
        filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return csv_bytes, filename

    async def _build_chart_only(self, req, charts):
        if charts:
            # Return the first chart as PNG
            chart_bytes, title = charts[0]
            filename = f"chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            return chart_bytes, filename
        else:
            # Generate a default chart
            kpis = self.data_engine.extract_kpis(req.answer)
            if kpis:
                chart = self.chart_engine.create_summary_chart(kpis)
                filename = f"chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                return chart, filename
            raise ValueError("No chartable data found in the answer")


# ── Singleton ────────────────────────────────────────────────
_report_service: Optional[ReportService] = None


def get_report_service() -> ReportService:
    global _report_service
    if _report_service is None:
        _report_service = ReportService()
    return _report_service
