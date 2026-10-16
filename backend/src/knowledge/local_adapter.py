"""Local backend: Qdrant hybrid index + NVIDIA reranker."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from src.contracts import RetrievalRequest, RetrievalResult
from src.core.config import settings
from src.retrieval import ContextBuilder, HybridRetriever, get_hybrid_retriever

from .base import AdapterCapabilities, KnowledgeAdapter


class LocalKnowledgeAdapter(KnowledgeAdapter):
    name = "local"

    def __init__(self, retriever: Optional[HybridRetriever] = None):
        self._retriever = retriever
        self.context_builder = ContextBuilder()

    @property
    def retriever(self) -> HybridRetriever:
        if self._retriever is None:
            self._retriever = get_hybrid_retriever()
        return self._retriever

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        started = time.perf_counter()
        chunks = await self.retriever.retrieve(
            query=request.query,
            top_k=request.top_k,
            filters=request.filters,
            rerank=request.rerank,
            alternate_queries=request.alternate_queries,
        )
        built = self.context_builder.build(chunks, max_tokens=max(256, request.max_context_chars // 4))
        return RetrievalResult(
            query=request.query,
            chunks=built.chunks,
            backend=self.name,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            context=built.text,
            executed_queries=[request.query] + list(request.alternate_queries),
            metadata={"candidates": len(chunks), "context_tokens": built.tokens, "truncated": built.truncated},
        )

    async def healthcheck(self) -> Dict[str, Any]:
        ok = await self.retriever.store.healthcheck()
        info: Dict[str, Any] = {"backend": self.name, "status": "healthy" if ok else "unhealthy"}
        if ok:
            try:
                store_info = await self.retriever.store.info()
                info["collection_status"] = store_info.pop("status", None)
                info.update(store_info)
            except Exception as exc:
                info["detail"] = str(exc)
        return info

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            hybrid_search=settings.hybrid_search_enabled,
            reranking=settings.enable_reranking and settings.reranker_backend != "none",
            query_planning=False,
            multimodal=False,
            permission_filters=True,
            returns_context=True,
            ingestion=True,
        )
