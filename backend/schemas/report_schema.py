"""
Report Generation Schemas.

Pydantic models for report requests, responses, and options.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import uuid


class ReportFormat(str, Enum):
    PDF = "pdf"
    EXCEL = "excel"
    WORD = "word"
    CSV = "csv"
    CHART = "chart"


class ChartType(str, Enum):
    BAR = "bar"
    HORIZONTAL_BAR = "hbar"
    LINE = "line"
    PIE = "pie"
    STACKED_BAR = "stacked_bar"
    GAUGE = "gauge"
    TABLE = "table_chart"


class ReportTemplate(str, Enum):
    DEFAULT = "default"
    FINANCIAL = "financial"
    SAFETY = "safety"
    EXECUTIVE = "executive"


class ReportOptions(BaseModel):
    """Options for report generation."""
    include_charts: bool = True
    include_sources: bool = True
    include_metadata: bool = True
    template: ReportTemplate = ReportTemplate.DEFAULT
    chart_types: List[ChartType] = Field(default_factory=lambda: [ChartType.BAR, ChartType.PIE])
    brand_color: str = "#3C8C81"
    accent_color: str = "#2D6A5F"


class SourceChunk(BaseModel):
    """A source chunk from RAG retrieval."""
    content: str
    page: int = 0
    source: str = ""
    score: float = 0.0
    content_type: str = "text"


class ReportRequest(BaseModel):
    """Request to generate a report."""
    report_type: ReportFormat = ReportFormat.PDF
    title: str = "RAG Analysis Report"
    query: str
    answer: str
    sources: List[SourceChunk] = Field(default_factory=list)
    options: ReportOptions = Field(default_factory=ReportOptions)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReportStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


class ReportResponse(BaseModel):
    """Response after report generation."""
    report_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: ReportStatus = ReportStatus.QUEUED
    download_url: Optional[str] = None
    filename: str = ""
    format: ReportFormat = ReportFormat.PDF
    created_at: datetime = Field(default_factory=datetime.now)
    progress: int = 0
    error: Optional[str] = None
    file_size_kb: Optional[float] = None


class ReportListItem(BaseModel):
    """Summary item for report listing."""
    report_id: str
    title: str
    format: ReportFormat
    status: ReportStatus
    created_at: datetime
    filename: str
    file_size_kb: Optional[float] = None
