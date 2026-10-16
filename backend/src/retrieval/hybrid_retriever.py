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

REWRITE_PROMPT = """Rewrite the search query below so it matches how the information would be phrased inside business documents.
Keep every specific term (names, numbers, dates, codes). Expand abbreviations. Return ONLY the rewritten query, one line.

Query: {query}"""

from .fusion import dedupe_chunks, reciprocal_rank_fusion

logger = get_logger(__name__)


class HybridRetriever:
    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        reranker: Optional[RerankerService] = None,
        store=None,
        llm=None,
    ):
        self.embedding = embedding_service or get_embedding_service()
        self.reranker = reranker or get_reranker_service()
        self.store = store or get_qdrant_store()
        self.sparse = SparseEncoder()
        self._llm = llm
        self.last_trace: dict = {}

    @property
    def llm(self):
        if self._llm is None:
            from src.services.llm.nvidia_llm_service import get_llm_service
            self._llm = get_llm_service()
        return self._llm

    async def rewrite_query(self, query: str) -> Optional[str]:
        """Ask the fast model for a document-style rephrasing (used by the relevance gate)."""
        try:
            text = await self.llm.generate(REWRITE_PROMPT.format(query=query), max_tokens=80, temperature=0.2, fast=True)
            text = text.strip().strip('"').splitlines()[0].strip() if text else ""
            return text if text and text.lower() != query.lower() else None
        except Exception as exc:
            logger.debug("Query rewrite failed", error=str(exc))
            return None

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
        include_summaries: bool = False,
        adaptive: Optional[bool] = None,
    ) -> List[RetrievedChunk]:
        """Return the best ``top_k`` chunks for the query (with an optional relevance-gated retry)."""
        adaptive = settings.adaptive_retrieval_enabled if adaptive is None else adaptive
        self.last_trace = {"attempts": 1, "rewritten": None, "gated": False}
        results = await self._retrieve_once(query, top_k, filters, rerank, alternate_queries, candidate_k, include_summaries)
        if not adaptive or not rerank or settings.reranker_backend == "none":
            return results
        top = max((c.rerank_score or 0.0) for c in results) if results else 0.0
        if results and top >= settings.relevance_gate_threshold:
            return results
        # CRAG-style gate: weak or no evidence → rewrite once and fuse both attempts
        for _ in range(settings.adaptive_max_retries):
            rewritten = await self.rewrite_query(query)
            if not rewritten:
                break
            self.last_trace.update({"attempts": self.last_trace["attempts"] + 1, "rewritten": rewritten, "gated": True})
            retry = await self._retrieve_once(rewritten, top_k, filters, rerank, [query], candidate_k, include_summaries)
            if retry:
                merged = dedupe_chunks(reciprocal_rank_fusion([retry, results], k=settings.rrf_k) if results else retry)
                for c in merged:
                    c.metadata["adaptive_retry"] = True
                results = merged[:top_k]
                if max((c.rerank_score or 0.0) for c in results) >= settings.relevance_gate_threshold:
                    break
        return results

    async def _retrieve_once(
        self,
        query: str,
        top_k: Optional[int],
        filters: Optional[RetrievalFilters],
        rerank: bool,
        alternate_queries: Optional[List[str]],
        candidate_k: Optional[int],
        include_summaries: bool,
    ) -> List[RetrievedChunk]:
        started = time.perf_counter()
        top_k = top_k or settings.rerank_top_k
        candidate_k = candidate_k or max(settings.top_k_retrieval, top_k * 3)

        queries = [query] + [q for q in (alternate_queries or []) if q and q.strip() and q.strip() != query.strip()]
        queries = queries[: 1 + settings.max_sub_queries]

        searches = [self._search_one(q, candidate_k, filters) for q in queries]
        if include_summaries:
            # dedicated prefetch of document-outline chunks so overview questions see every document
            summary_filters = (filters.model_copy(deep=True) if filters else RetrievalFilters())
            summary_filters.metadata = {**summary_filters.metadata, "chunk_level": "document_summary"}
            searches.append(self._search_one(query, max(top_k, 10), summary_filters))
            queries = queries + [f"{query} [summaries]"]
        results = await asyncio.gather(*searches, return_exceptions=True)
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
