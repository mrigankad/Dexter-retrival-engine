"""In-memory keyword-overlap adapter for tests, demos and offline development."""

from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Optional

from src.contracts import RetrievalRequest, RetrievalResult, RetrievedChunk
from src.infrastructure.vector_store.sparse_encoder import tokenize

from .base import AdapterCapabilities, KnowledgeAdapter


class MockKnowledgeAdapter(KnowledgeAdapter):
    name = "mock"

    def __init__(self, documents: Optional[Iterable[Dict[str, Any]]] = None):
        self._docs: List[Dict[str, Any]] = []
        for d in documents or []:
            self.add(**d)

    def add(self, content: str, source: str = "mock.txt", document_id: Optional[str] = None,
            page: Optional[int] = None, **metadata: Any) -> None:
        self._docs.append({
            "id": f"mock_{len(self._docs)}", "content": content, "source": source,
            "document_id": document_id or source, "page": page, "metadata": metadata,
        })

    def clear(self) -> None:
        self._docs.clear()

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        started = time.perf_counter()
        q_tokens = set(tokenize(request.query))
        for alt in request.alternate_queries:
            q_tokens |= set(tokenize(alt))
        scored: List[RetrievedChunk] = []
        for d in self._docs:
            if request.filters.document_ids and d["document_id"] not in request.filters.document_ids:
                continue
            d_tokens = set(tokenize(d["content"]))
            overlap = len(q_tokens & d_tokens)
            if overlap == 0:
                continue
            score = overlap / max(1, len(q_tokens))
            scored.append(RetrievedChunk(
                id=d["id"], content=d["content"], score=score, source=d["source"],
                document_id=d["document_id"], page=d["page"], backend=self.name, metadata=dict(d["metadata"]),
            ))
        scored.sort(key=lambda c: c.score, reverse=True)
        chunks = scored[: request.top_k]
        context = "\n\n---\n\n".join(f"[{i + 1}] {c.source}\n{c.content}" for i, c in enumerate(chunks))
        return RetrievalResult(
            query=request.query, chunks=chunks, backend=self.name,
            latency_ms=round((time.perf_counter() - started) * 1000, 2), context=context,
            executed_queries=[request.query], metadata={"documents": len(self._docs)},
        )

    async def healthcheck(self) -> Dict[str, Any]:
        return {"backend": self.name, "status": "healthy", "documents": len(self._docs)}

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(returns_context=True, ingestion=True)
