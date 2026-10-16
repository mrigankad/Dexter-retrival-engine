"""Evidence envelope: the normalized unit the synthesizer cites and the UI shows."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

from .retrieval import RetrievedChunk


class EvidenceLocator(BaseModel):
    document_id: Optional[str] = None
    page: Optional[int] = None
    total_pages: Optional[int] = None
    chunk_index: Optional[int] = None
    section: Optional[str] = None
    url: Optional[str] = None
    query_id: Optional[str] = None   # for structured-data evidence (reserved)


class Evidence(BaseModel):
    id: str                                   # e.g. "ev_3"
    type: Literal["document", "sql", "web", "memory"] = "document"
    source_name: str
    title: Optional[str] = None
    locator: EvidenceLocator = Field(default_factory=EvidenceLocator)
    snippet: str = ""
    score: float = 0.0
    rerank_score: Optional[float] = None
    backend: str = "local"
    content_type: str = "text"
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_chunk(cls, idx: int, chunk: RetrievedChunk, snippet_chars: int = 400) -> "Evidence":
        return cls(
            id=f"ev_{idx}",
            type="document",
            source_name=chunk.source,
            title=chunk.metadata.get("title"),
            locator=EvidenceLocator(
                document_id=chunk.document_id,
                page=chunk.page,
                total_pages=chunk.total_pages,
                chunk_index=chunk.chunk_index,
                section=" > ".join(chunk.section_path) if chunk.section_path else None,
                url=chunk.metadata.get("url"),
            ),
            snippet=chunk.content[:snippet_chars],
            score=chunk.score,
            rerank_score=chunk.rerank_score,
            backend=chunk.backend,
            content_type=chunk.content_type,
            metadata={k: v for k, v in chunk.metadata.items() if k not in {"title", "url"}},
        )

    def to_legacy_source(self) -> Dict[str, Any]:
        """Shape the existing React UI expects in the `sources` event."""
        return {
            "source": self.source_name,
            "page": self.locator.page if self.locator.page is not None else "N/A",
            "total_pages": self.locator.total_pages if self.locator.total_pages is not None else "N/A",
            "chunk_index": self.locator.chunk_index or 0,
            "score": self.score,
            "rerank_score": self.rerank_score,
            "content_type": self.content_type,
            "document_id": self.locator.document_id,
            "snippet": self.snippet,
            "evidence_id": self.id,
            "backend": self.backend,
        }


class Citation(BaseModel):
    """A citation marker found in the final answer, resolved to evidence."""
    marker: str          # e.g. "[3]"
    evidence_id: str     # e.g. "ev_3"
    resolved: bool = True
