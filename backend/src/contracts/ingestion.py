"""Ingestion contracts: parsed documents, chunks, jobs."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .common import ChunkLevel, ContentType


class ParsedPage(BaseModel):
    page: int
    text: str
    tables: List[str] = Field(default_factory=list)      # markdown tables found on the page
    headings: List[str] = Field(default_factory=list)


class ParsedDocument(BaseModel):
    filename: str
    file_type: str
    pages: List[ParsedPage]
    title: Optional[str] = None
    parser: str = "unknown"
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def total_pages(self) -> int:
        return len(self.pages)

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.pages)


class Chunk(BaseModel):
    id: str
    document_id: str
    content: str                       # text that is embedded (may include contextual header)
    raw_content: str                   # text without the contextual header (shown to users)
    chunk_index: int
    page: Optional[int] = None
    total_pages: Optional[int] = None
    content_type: ContentType = ContentType.TEXT
    chunk_level: ChunkLevel = ChunkLevel.PARAGRAPH
    section_path: List[str] = Field(default_factory=list)
    source: str = ""
    token_estimate: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IngestionJob(BaseModel):
    document_id: str
    file_path: str
    filename: str
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IngestionResult(BaseModel):
    document_id: str
    status: str
    chunks_count: int = 0
    total_pages: int = 0
    parser: str = "unknown"
    duration_ms: float = 0.0
    error: Optional[str] = None
    stats: Dict[str, Any] = Field(default_factory=dict)
