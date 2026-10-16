"""
Compatibility facade used by the legacy multi-agent package.

Wraps the configured ``KnowledgeAdapter`` and returns the dict shape the
agents expect: ``{"documents": [...], "scores": [...]}``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.contracts import RetrievalFilters, RetrievalRequest
from src.knowledge import get_knowledge_adapter


class RetrievalService:
    def __init__(self, backend: Optional[str] = None):
        self.backend = backend

    async def retrieve(self, query: str, top_k: int = 12, document_ids: Optional[List[str]] = None,
                       rerank: bool = True) -> Dict[str, Any]:
        adapter = get_knowledge_adapter(self.backend)
        result = await adapter.retrieve(RetrievalRequest(
            query=query, top_k=top_k, rerank=rerank, filters=RetrievalFilters(document_ids=document_ids or None),
        ))
        return {
            "documents": [
                {"id": c.id, "title": c.source, "content": c.content, "page": c.page, "document_id": c.document_id,
                 "score": c.score, "rerank_score": c.rerank_score, "backend": c.backend}
                for c in result.chunks
            ],
            "scores": [c.rerank_score if c.rerank_score is not None else c.score for c in result.chunks],
            "context": result.context,
            "backend": result.backend,
        }

    async def retrieve_with_context(self, query: str, top_k: Optional[int] = None, **_: Any) -> str:
        return (await self.retrieve(query, top_k=top_k or 12)).get("context") or ""
