"""Retrieval request / result contracts (the KnowledgeAdapter interface types)."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


ReasoningEffort = Literal["minimal", "low", "medium"]


class RetrievalFilters(BaseModel):
    """Backend-agnostic filters. Adapters translate what they support."""
    document_ids: Optional[List[str]] = None
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    content_types: Optional[List[str]] = None
    page: Optional[int] = None
    # Access control: chunk must carry at least one of these principals in its ``acl`` payload.
    principals: Optional[List[str]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def is_empty(self) -> bool:
        return not any([self.document_ids, self.tenant_id, self.user_id, self.content_types, self.page,
                        self.principals, self.metadata])


class RetrievalRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=8, ge=1, le=100)
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    rerank: bool = True
    reasoning_effort: ReasoningEffort = "low"
    # Optional extra query phrasings (multi-query). Adapters may fuse them.
    alternate_queries: List[str] = Field(default_factory=list)
    # Max characters of context an adapter should return for synthesis.
    max_context_chars: int = 24_000


class RetrievedChunk(BaseModel):
    """One unit of evidence returned by any backend."""
    id: str
    content: str
    score: float = 0.0
    rerank_score: Optional[float] = None
    dense_score: Optional[float] = None
    sparse_score: Optional[float] = None
    source: str = "unknown"                  # file name / URL / title
    document_id: Optional[str] = None
    page: Optional[int] = None
    total_pages: Optional[int] = None
    chunk_index: Optional[int] = None
    content_type: str = "text"
    section_path: List[str] = Field(default_factory=list)
    backend: str = "local"
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def citation_label(self) -> str:
        if self.page is not None:
            return f"{self.source}, p.{self.page}"
        return self.source


class RetrievalResult(BaseModel):
    query: str
    chunks: List[RetrievedChunk] = Field(default_factory=list)
    backend: str = "local"
    latency_ms: float = 0.0
    # Optional pre-assembled context string (Foundry IQ style extractive output).
    context: Optional[str] = None
    # Query rewrites / sub-queries actually executed by the backend.
    executed_queries: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return len(self.chunks) == 0
