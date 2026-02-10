"""
Multi-Hop Feedback Loop - Missing Evidence Retry Engine.

Handles cases where initial retrieval yields insufficient evidence:
1. Detects insufficient evidence conditions
2. Generates reformulated queries
3. Broadens search with expanded filters
4. Iteratively retries with relaxed constraints
5. Tracks retry budget
"""

from typing import Any, Dict, List, Optional, Tuple
import asyncio

from core.config import settings
from core.logger import get_logger, log_timing
from services.retrieval_service import RetrievalService
from services.context_compressor import ContextCompressor

logger = get_logger(__name__)


class FeedbackResult:
    """Result of a feedback loop iteration."""

    def __init__(
        self,
        query: str,
        evidence: str,
        sources: List[Dict[str, Any]],
        iteration: int,
        strategy_used: str,
        success: bool,
    ):
        self.query = query
        self.evidence = evidence
        self.sources = sources
        self.iteration = iteration
        self.strategy_used = strategy_used
        self.success = success


class FeedbackLoop:
    """
    Multi-hop feedback loop for handling missing evidence.
    
    Retry Strategies (escalating):
    1. BROADEN: Remove content-type filters, increase top_k
    2. REFORMULATE: Rephrase the query using LLM
    3. DECOMPOSE: Break the failed query into smaller pieces
    4. SEMANTIC_FALLBACK: Use the original query with maximum recall
    
    Budget: Maximum 3 retry iterations per sub-query.
    """

    def __init__(
        self,
        retrieval_service: Optional[RetrievalService] = None,
        llm_service=None,
        max_retries: int = 3,
    ):
        self.retrieval = retrieval_service or RetrievalService()
        self.llm = llm_service
        self.compressor = ContextCompressor(llm_service=llm_service)
        self.max_retries = max_retries
        
        self._strategies = [
            "broaden",
            "reformulate",
            "decompose",
            "semantic_fallback",
        ]

    @log_timing("feedback_loop")
    async def retry_missing_evidence(
        self,
        original_query: str,
        failed_sub_queries: List[str],
        original_context: str = "",
        min_evidence_tokens: int = 50,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Retry retrieval for sub-queries that yielded insufficient evidence.
        
        Args:
            original_query: The original user query
            failed_sub_queries: Sub-queries that returned no/insufficient evidence
            original_context: Context already gathered (to avoid redundancy)
            min_evidence_tokens: Minimum token threshold for "sufficient" evidence
            
        Returns:
            Tuple of (additional_context, additional_sources)
        """
        if not failed_sub_queries:
            return "", []

        logger.info(
            "Feedback loop activated",
            failed_queries=len(failed_sub_queries),
            max_retries=self.max_retries,
        )

        all_additional_context = []
        all_additional_sources = []

        for sub_query in failed_sub_queries:
            result = await self._retry_single_query(
                sub_query,
                original_query,
                original_context,
                min_evidence_tokens,
            )
            
            if result and result.success:
                all_additional_context.append(
                    f"### Recovered Evidence ({result.strategy_used}, retry #{result.iteration}): "
                    f"'{result.query}'\n{result.evidence}"
                )
                all_additional_sources.extend(result.sources)

        additional_context = "\n\n".join(all_additional_context)
        
        logger.info(
            "Feedback loop complete",
            recovered_queries=len(all_additional_context),
            total_failed=len(failed_sub_queries),
        )

        return additional_context, all_additional_sources

    async def _retry_single_query(
        self,
        sub_query: str,
        original_query: str,
        existing_context: str,
        min_tokens: int,
    ) -> Optional[FeedbackResult]:
        """Retry a single sub-query with escalating strategies."""
        
        for iteration, strategy in enumerate(self._strategies[:self.max_retries], 1):
            try:
                result = await self._execute_strategy(
                    strategy, sub_query, original_query, iteration
                )
                
                if result and result.success:
                    # Check if we got sufficient evidence
                    evidence_tokens = len(result.evidence) // 4
                    if evidence_tokens >= min_tokens:
                        logger.info(
                            "Evidence recovered",
                            strategy=strategy,
                            iteration=iteration,
                            tokens=evidence_tokens,
                        )
                        return result
                    else:
                        logger.debug(
                            "Insufficient evidence from strategy",
                            strategy=strategy,
                            tokens=evidence_tokens,
                        )
                        
            except Exception as e:
                logger.warning(
                    "Retry strategy failed",
                    strategy=strategy,
                    iteration=iteration,
                    error=str(e),
                )

        logger.warning("All retry strategies exhausted", sub_query=sub_query[:80])
        return None

    async def _execute_strategy(
        self,
        strategy: str,
        sub_query: str,
        original_query: str,
        iteration: int,
    ) -> Optional[FeedbackResult]:
        """Execute a specific retry strategy."""
        
        if strategy == "broaden":
            return await self._strategy_broaden(sub_query, iteration)
        elif strategy == "reformulate":
            return await self._strategy_reformulate(sub_query, original_query, iteration)
        elif strategy == "decompose":
            return await self._strategy_decompose(sub_query, iteration)
        elif strategy == "semantic_fallback":
            return await self._strategy_semantic_fallback(original_query, iteration)
        
        return None

    async def _strategy_broaden(
        self, query: str, iteration: int
    ) -> Optional[FeedbackResult]:
        """Strategy 1: Broaden search by removing filters and increasing top_k."""
        logger.debug("Trying BROADEN strategy", query=query[:80])
        
        # Retrieve with no filters and higher top_k
        docs = await self.retrieval.retrieve(
            query=query,
            top_k=settings.top_k_retrieval * 2,  # Double the usual
            rerank=True,
            filter_conditions=None,  # No filters
        )

        if not docs:
            return FeedbackResult(
                query=query, evidence="", sources=[],
                iteration=iteration, strategy_used="broaden", success=False,
            )

        # Compress
        compressed = await self.compressor.compress(
            sub_query=query, retrieved_docs=docs, max_tokens=400
        )

        sources = self._extract_sources(docs)

        return FeedbackResult(
            query=query,
            evidence=compressed.compressed_text,
            sources=sources,
            iteration=iteration,
            strategy_used="broaden",
            success=bool(compressed.compressed_text.strip()),
        )

    async def _strategy_reformulate(
        self, query: str, original_query: str, iteration: int
    ) -> Optional[FeedbackResult]:
        """Strategy 2: Use LLM to rephrase the query."""
        if not self.llm:
            return None

        logger.debug("Trying REFORMULATE strategy", query=query[:80])

        try:
            reformulate_prompt = f"""The following query failed to find relevant evidence in a document search.
Rephrase it to be more likely to match document content.

Original full question: {original_query}
Failed sub-query: {query}

Consider:
- Use more general terms
- Remove overly specific constraints
- Focus on the core concept
- Use synonyms for technical terms

Rephrased query (output ONLY the new query, nothing else):"""

            rephrased = await self.llm.generate(
                prompt=reformulate_prompt,
                max_tokens=100,
                temperature=0.3,
            )
            rephrased = rephrased.strip()

            if not rephrased or rephrased == query:
                return None

            # Retrieve with rephrased query
            docs = await self.retrieval.retrieve(
                query=rephrased,
                top_k=settings.top_k_retrieval,
                rerank=True,
            )

            if not docs:
                return FeedbackResult(
                    query=rephrased, evidence="", sources=[],
                    iteration=iteration, strategy_used="reformulate", success=False,
                )

            compressed = await self.compressor.compress(
                sub_query=query, retrieved_docs=docs, max_tokens=400
            )

            return FeedbackResult(
                query=rephrased,
                evidence=compressed.compressed_text,
                sources=self._extract_sources(docs),
                iteration=iteration,
                strategy_used="reformulate",
                success=bool(compressed.compressed_text.strip()),
            )

        except Exception as e:
            logger.warning("Reformulation failed", error=str(e))
            return None

    async def _strategy_decompose(
        self, query: str, iteration: int
    ) -> Optional[FeedbackResult]:
        """Strategy 3: Break the query into simpler pieces."""
        if not self.llm:
            return None

        logger.debug("Trying DECOMPOSE strategy", query=query[:80])

        try:
            decompose_prompt = f"""Break this query into 2-3 simpler search queries that would find the needed information:

Query: {query}

Output each query on a separate line. Output ONLY the queries, nothing else:"""

            response = await self.llm.generate(
                prompt=decompose_prompt,
                max_tokens=200,
                temperature=0.2,
            )

            sub_queries = [
                line.strip().lstrip("- ").lstrip("0123456789.)")
                for line in response.strip().split("\n")
                if line.strip() and len(line.strip()) > 10
            ][:3]

            if not sub_queries:
                return None

            # Execute all mini-queries in parallel
            tasks = [
                self.retrieval.retrieve(
                    query=sq, top_k=5, rerank=True
                )
                for sq in sub_queries
            ]
            all_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Collect all docs
            all_docs = []
            for result in all_results:
                if isinstance(result, list):
                    all_docs.extend(result)

            if not all_docs:
                return FeedbackResult(
                    query=query, evidence="", sources=[],
                    iteration=iteration, strategy_used="decompose", success=False,
                )

            compressed = await self.compressor.compress(
                sub_query=query, retrieved_docs=all_docs[:10], max_tokens=400
            )

            return FeedbackResult(
                query=query,
                evidence=compressed.compressed_text,
                sources=self._extract_sources(all_docs[:10]),
                iteration=iteration,
                strategy_used="decompose",
                success=bool(compressed.compressed_text.strip()),
            )

        except Exception as e:
            logger.warning("Decomposition failed", error=str(e))
            return None

    async def _strategy_semantic_fallback(
        self, original_query: str, iteration: int
    ) -> Optional[FeedbackResult]:
        """Strategy 4: Fall back to broad semantic search on original query."""
        logger.debug("Trying SEMANTIC_FALLBACK strategy")

        docs = await self.retrieval.retrieve(
            query=original_query,
            top_k=settings.top_k_retrieval * 3,  # Maximum recall
            rerank=True,
            filter_conditions=None,
        )

        if not docs:
            return FeedbackResult(
                query=original_query, evidence="", sources=[],
                iteration=iteration, strategy_used="semantic_fallback", success=False,
            )

        # Use retrieve_with_context for a formatted output
        context = await self.retrieval.retrieve_with_context(
            query=original_query,
            max_tokens=2048,
        )

        return FeedbackResult(
            query=original_query,
            evidence=context if context else "",
            sources=self._extract_sources(docs),
            iteration=iteration,
            strategy_used="semantic_fallback",
            success=bool(context),
        )

    @staticmethod
    def _extract_sources(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract source metadata from retrieved documents."""
        sources = []
        for doc in docs:
            payload = doc.get("payload", {})
            sources.append({
                "source": payload.get("source", "Unknown"),
                "page": payload.get("page", "N/A"),
                "total_pages": payload.get("total_pages", "N/A"),
                "chunk_index": payload.get("chunk_index", 0),
                "document_id": payload.get("document_id"),
                "score": doc.get("score", 0),
                "content_type": payload.get("content_type", "text"),
            })
        return sources
