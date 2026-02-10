"""
Multi-Hop Executor - Parallel Sub-Query Execution Engine.

Executes query plans with:
- Parallel sub-query retrieval via asyncio.gather
- Content-type-aware retrieval
- Integrated context compression
- Cross-query deduplication
- Evidence assembly pipeline
- Observability hooks
"""

from typing import Any, Dict, List, Optional, Tuple
import asyncio
import time

from core.config import settings
from core.logger import get_logger, log_timing
from core.telemetry import get_rag_metrics, Timer
from services.retrieval_service import RetrievalService
from services.context_compressor import ContextCompressor, CompressedEvidence
from services.planner_service import QueryPlan, SubQuery

logger = get_logger(__name__)


class SubQueryResult:
    """Result of a single sub-query execution."""

    def __init__(
        self,
        sub_query: SubQuery,
        raw_docs: List[Dict[str, Any]],
        compressed_evidence: Optional[CompressedEvidence] = None,
        execution_time_ms: float = 0,
        success: bool = True,
        error: Optional[str] = None,
    ):
        self.sub_query = sub_query
        self.raw_docs = raw_docs
        self.compressed_evidence = compressed_evidence
        self.execution_time_ms = execution_time_ms
        self.success = success
        self.error = error

    @property
    def evidence_text(self) -> str:
        """Get the compressed evidence text."""
        if self.compressed_evidence:
            return self.compressed_evidence.compressed_text
        return ""

    @property
    def sources(self) -> List[Dict[str, Any]]:
        """Extract source metadata from raw docs."""
        sources = []
        for doc in self.raw_docs:
            payload = doc.get("payload", {})
            sources.append({
                "source": payload.get("source", "Unknown"),
                "page": payload.get("page", "N/A"),
                "total_pages": payload.get("total_pages", "N/A"),
                "chunk_index": payload.get("chunk_index", 0),
                "document_id": payload.get("document_id"),
                "score": doc.get("score", 0),
                "rerank_score": doc.get("rerank_score"),
                "content_type": payload.get("content_type", "text"),
            })
        return sources


class MultiHopExecutor:
    """
    Parallel sub-query execution engine.
    
    Execution Pipeline:
    1. Parse plan into executable sub-queries
    2. Build filter conditions per sub-query
    3. Execute all sub-queries in parallel (asyncio.gather)
    4. Compress evidence per sub-query (with dedup)
    5. Assemble multi-hop evidence context
    6. Track metrics
    """

    def __init__(
        self,
        retrieval_service: Optional[RetrievalService] = None,
        llm_service=None,
        max_concurrent: int = 5,
        tokens_per_sub_query: int = 300,
    ):
        self.retrieval = retrieval_service or RetrievalService()
        self.compressor = ContextCompressor(llm_service=llm_service)
        self.max_concurrent = max_concurrent
        self.tokens_per_sq = tokens_per_sub_query
        self.metrics = get_rag_metrics()

    @log_timing("multi_hop_execute")
    async def execute_plan(
        self,
        plan: QueryPlan,
        top_k_per_query: int = 8,
        compress: bool = True,
    ) -> Tuple[str, List[Dict[str, Any]], List[SubQueryResult]]:
        """
        Execute a query plan with parallel sub-query retrieval.
        
        Args:
            plan: The QueryPlan from the planner
            top_k_per_query: Number of chunks per sub-query
            compress: Whether to apply context compression
            
        Returns:
            Tuple of (assembled_context, all_sources, sub_query_results)
        """
        start_time = time.time()
        self.compressor.reset_dedup()

        sub_queries = plan.sub_queries
        if not sub_queries:
            return "", [], []

        logger.info(
            "Executing multi-hop plan",
            sub_queries=len(sub_queries),
            query_type=plan.query_type,
            reasoning=plan.reasoning[:100],
        )

        # Step 1: Execute all sub-queries in parallel
        semaphore = asyncio.Semaphore(self.max_concurrent)
        tasks = [
            self._execute_sub_query(sq, semaphore, top_k_per_query)
            for sq in sub_queries
        ]
        results: List[SubQueryResult] = await asyncio.gather(*tasks)

        # Step 2: Compress evidence (with cross-query dedup)
        if compress:
            results = await self._compress_results(results)

        # Step 3: Assemble context
        context = self._assemble_evidence(results, plan)
        all_sources = self._collect_sources(results)

        # Step 4: Metrics
        elapsed_ms = (time.time() - start_time) * 1000
        successful = sum(1 for r in results if r.success)
        total_docs = sum(len(r.raw_docs) for r in results)

        logger.info(
            "Multi-hop execution complete",
            elapsed_ms=round(elapsed_ms),
            sub_queries_executed=len(results),
            successful=successful,
            total_docs_retrieved=total_docs,
            total_sources=len(all_sources),
        )

        return context, all_sources, results

    async def _execute_sub_query(
        self,
        sub_query: SubQuery,
        semaphore: asyncio.Semaphore,
        top_k: int,
    ) -> SubQueryResult:
        """Execute a single sub-query with semaphore-controlled concurrency."""
        start = time.time()

        async with semaphore:
            try:
                # Build filter conditions
                filter_cond = self._build_filters(sub_query)

                # Extract keywords for hybrid search
                keywords = None
                if hasattr(sub_query, 'filters') and sub_query.filters:
                    keywords = getattr(sub_query.filters, 'keywords', None)

                # Retrieve
                raw_docs = await self.retrieval.retrieve(
                    query=sub_query.question,
                    top_k=top_k,
                    rerank=settings.enable_reranking,
                    filter_conditions=filter_cond if filter_cond else None,
                    keywords=keywords,
                )

                elapsed = (time.time() - start) * 1000

                logger.debug(
                    "Sub-query executed",
                    question=sub_query.question[:80],
                    docs_found=len(raw_docs),
                    elapsed_ms=round(elapsed),
                )

                return SubQueryResult(
                    sub_query=sub_query,
                    raw_docs=raw_docs,
                    execution_time_ms=elapsed,
                    success=True,
                )

            except Exception as e:
                elapsed = (time.time() - start) * 1000
                logger.error(
                    "Sub-query failed",
                    question=sub_query.question[:80],
                    error=str(e),
                )
                return SubQueryResult(
                    sub_query=sub_query,
                    raw_docs=[],
                    execution_time_ms=elapsed,
                    success=False,
                    error=str(e),
                )

    async def _compress_results(
        self, results: List[SubQueryResult]
    ) -> List[SubQueryResult]:
        """Apply context compression to all sub-query results."""
        for result in results:
            if result.success and result.raw_docs:
                compressed = await self.compressor.compress(
                    sub_query=result.sub_query.question,
                    retrieved_docs=result.raw_docs,
                    max_tokens=self.tokens_per_sq,
                )
                result.compressed_evidence = compressed
        return results

    def _assemble_evidence(
        self, results: List[SubQueryResult], plan: QueryPlan
    ) -> str:
        """Assemble compressed evidence into a unified context block."""
        context_parts = []

        for i, result in enumerate(results, 1):
            if not result.success:
                context_parts.append(
                    f"### Evidence {i}: Sub-query '{result.sub_query.question}'\n"
                    f"[RETRIEVAL FAILED: {result.error}]"
                )
                continue

            if not result.evidence_text:
                context_parts.append(
                    f"### Evidence {i}: Sub-query '{result.sub_query.question}'\n"
                    f"[NO EVIDENCE FOUND]"
                )
                continue

            # Add compression metadata
            meta = ""
            if result.compressed_evidence:
                ce = result.compressed_evidence
                meta = f" (Compressed {ce.compression_ratio:.0%}, {ce.dedup_removed} deduped)"

            context_parts.append(
                f"### Evidence {i}: Sub-query '{result.sub_query.question}'{meta}\n"
                f"{result.evidence_text}"
            )

        return "\n\n".join(context_parts)

    def _collect_sources(
        self, results: List[SubQueryResult]
    ) -> List[Dict[str, Any]]:
        """Collect and deduplicate sources from all sub-query results."""
        all_sources = []
        seen_keys = set()

        for result in results:
            for source in result.sources:
                # Dedup by (doc_id, page, chunk_index)
                key = (
                    source.get("document_id", ""),
                    source.get("page", ""),
                    source.get("chunk_index", ""),
                )
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_sources.append(source)

        # Sort by score (descending)
        all_sources.sort(key=lambda x: x.get("score", 0), reverse=True)
        return all_sources

    @staticmethod
    def _build_filters(sub_query: SubQuery) -> Dict:
        """Build Qdrant filter conditions from sub-query filters."""
        filters = {}

        if hasattr(sub_query, 'page_hint') and sub_query.page_hint:
            filters["page"] = sub_query.page_hint

        if hasattr(sub_query, 'filters') and sub_query.filters:
            flt = sub_query.filters
            if hasattr(flt, 'content_type') and flt.content_type:
                filters["content_type"] = flt.content_type
            if hasattr(flt, 'section') and flt.section:
                filters["section_title"] = flt.section

        return filters
