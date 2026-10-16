"""
Hybrid retriever: the local engine's core search routine.

query (+ alternates) → dense embed + sparse encode → Qdrant prefetch/RRF per
query → RRF across queries → de-dup → rerank (NVIDIA NIM or local) → top-k.
"""

from __future__ import annotations

import asyncio
import time
from typing import List, Optional

from src.contracts import RetrievalFilters, RetrievedChunk
from src.core.config import settings
from src.core.logger import get_logger
from src.infrastructure.vector_store import SparseEncoder, get_qdrant_store
from src.services.llm.embedding_service import EmbeddingService, get_embedding_service
from src.services.llm.reranker_service import RerankerService, get_reranker_service

from .fusion import dedupe_chunks, reciprocal_rank_fusion

logger = get_logger(__name__)


class HybridRetriever:
    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        reranker: Optional[RerankerService] = None,
        store=None,
    ):
        self.embedding = embedding_service or get_embedding_service()
        self.reranker = reranker or get_reranker_service()
        self.store = store or get_qdrant_store()
        self.sparse = SparseEncoder()

    async def _search_one(self, query: str, top_k: int, filters: Optional[RetrievalFilters]) -> List[RetrievedChunk]:
        dense = await self.embedding.embed_query(query)
        sparse = self.sparse.encode_query(query) if settings.hybrid_search_enabled else None
        chunks = await self.store.hybrid_search(dense, sparse, top_k=top_k, filters=filters)
        for c in chunks:
            c.metadata["matched_query"] = query
        return chunks

    async def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[RetrievalFilters] = None,
        rerank: bool = True,
        alternate_queries: Optional[List[str]] = None,
        candidate_k: Optional[int] = None,
    ) -> List[RetrievedChunk]:
        """Return the best ``top_k`` chunks for the query."""
        started = time.perf_counter()
        top_k = top_k or settings.rerank_top_k
        candidate_k = candidate_k or max(settings.top_k_retrieval, top_k * 3)

        queries = [query] + [q for q in (alternate_queries or []) if q and q.strip() and q.strip() != query.strip()]
        queries = queries[: 1 + settings.max_sub_queries]

        results = await asyncio.gather(*(self._search_one(q, candidate_k, filters) for q in queries), return_exceptions=True)
        ranked_lists: List[List[RetrievedChunk]] = []
        for q, res in zip(queries, results):
            if isinstance(res, Exception):
                logger.warning("Sub-query search failed", query=q[:80], error=str(res))
                continue
            ranked_lists.append(res)
        if not ranked_lists:
            return []

        candidates = ranked_lists[0] if len(ranked_lists) == 1 else reciprocal_rank_fusion(ranked_lists, k=settings.rrf_k)
        candidates = dedupe_chunks(candidates)
        if settings.min_relevance_score > 0:
            candidates = [c for c in candidates if c.score >= settings.min_relevance_score]
        if not candidates:
            return []

        do_rerank = rerank and settings.enable_reranking and settings.reranker_backend != "none" and len(candidates) > 1
        if do_rerank:
            rankings = await self.reranker.rerank(query, [c.content for c in candidates], top_k=top_k)
            final: List[RetrievedChunk] = []
            for idx, _, score in rankings:
                chunk = candidates[idx]
                chunk.rerank_score = score if score else None
                final.append(chunk)
            # If the reranker failed it returns 0.0 scores in original order: keep fusion order.
            if all(c.rerank_score is None for c in final):
                final = candidates[:top_k]
        else:
            final = candidates[:top_k]

        logger.info(
            "Hybrid retrieval complete", queries=len(queries), candidates=len(candidates), returned=len(final),
            reranked=do_rerank, latency_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        return final


_default: Optional[HybridRetriever] = None


def get_hybrid_retriever() -> HybridRetriever:
    global _default
    if _default is None:
        _default = HybridRetriever()
    return _default


def reset_hybrid_retriever() -> None:
    global _default
    _default = None
