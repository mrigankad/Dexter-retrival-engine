"""
SearchAgent - Document Retrieval Specialist

Responsible for finding relevant documents using:
- Semantic search (vector similarity)
- Keyword search (BM25-style)
- Metadata filtering
- Reranking for better results
"""

from typing import Dict, Any, List, Optional
import time
import logging
from datetime import datetime

from src.agents.base.base_agent import Agent

logger = logging.getLogger(__name__)


class SearchAgent(Agent):
    """
    Finds relevant documents for a query.

    Uses the existing retrieval service to:
    1. Embed the query
    2. Search Qdrant for similar vectors
    3. Apply keyword scoring
    4. Combine and rank results
    """

    def __init__(self):
        super().__init__(
            name="SearchAgent",
            role="Information Retrieval Specialist"
        )
        self.tools = {
            "semantic_search":  None,  # Lazy-loaded
            "keyword_search":   None,
            "rerank":           None,
        }

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute search task.

        Args:
            task: {
                "task": "retrieve_documents",
                "query": "What is AI?",
                "top_k": 12,
                "previous_results": {...},  # Ignored by SearchAgent
                ...other metadata
            }

        Returns:
            {
                "documents": [...],
                "scores": [0.95, 0.87, ...],
                "search_strategy": "hybrid",
                "document_count": 12,
                "query": "What is AI?",
                "execution_time": 1.23
            }
        """
        if task.get("task") != "retrieve_documents":
            raise ValueError(f"SearchAgent only handles 'retrieve_documents' task")

        query = task.get("query", "")
        top_k = task.get("top_k", 12)

        if not query:
            raise ValueError("Query cannot be empty")

        logger.info(f"SearchAgent: Retrieving documents for query: {query}")

        start_time = time.time()

        try:
            # Import locally to avoid circular dependencies at module load
            from src.services.retrieval.retrieval_service import RetrievalService

            retrieval_svc = RetrievalService()

            # Execute retrieval using existing service
            results = await retrieval_svc.retrieve(
                query=query,
                top_k=top_k
            )

            duration = time.time() - start_time

            # Store execution in memory
            await self.observe({
                "type": "search_execution",
                "query": query,
                "top_k": top_k,
                "documents_found": len(results.get("documents", [])),
                "duration": duration,
                "importance": 0.6,
            })

            # Record execution
            self.record_execution(
                task_name="retrieve_documents",
                status="success",
                duration=duration,
                metadata={"query": query, "top_k": top_k}
            )

            # Update performance
            self.update_performance(
                success=True,
                quality_score=0.9,  # Assume good quality from retrieval service
                response_time=duration
            )

            return {
                "status": "success",
                "documents": results.get("documents", []),
                "scores": results.get("scores", []),
                "search_strategy": "hybrid",
                "document_count": len(results.get("documents", [])),
                "query": query,
                "execution_time": round(duration, 3),
                "metadata": {
                    "retrieval_method": "semantic_hybrid",
                    "timestamp": datetime.now().isoformat(),
                }
            }

        except Exception as exc:
            logger.error(f"SearchAgent failed: {exc}")

            duration = time.time() - start_time

            # Record failure
            self.record_execution(
                task_name="retrieve_documents",
                status="error",
                duration=duration,
                metadata={"query": query, "error": str(exc)}
            )

            # Update performance
            self.update_performance(
                success=False,
                quality_score=0.0,
                response_time=duration
            )

            raise

    async def think(self, query: str) -> Dict[str, Any]:
        """
        Determine search strategy for a query.

        Args:
            query: User's search query

        Returns:
            Strategy dict with parameters
        """
        strategy = {
            "use_semantic_search": True,
            "use_keyword_search": True,
            "use_reranking": True,
            "top_k": 12,
            "semantic_weight": 0.7,
            "keyword_weight": 0.3,
            "rerank_top_k": 6,
        }

        # Could enhance: analyze query complexity to adjust strategy
        query_length = len(query.split())
        if query_length > 15:
            strategy["top_k"] = 20  # Longer queries benefit from more results

        return strategy

    def get_search_stats(self) -> Dict[str, Any]:
        """Return search-specific statistics."""
        history = self.get_execution_history()
        successful_searches = sum(
            1 for h in history if h["status"] == "success"
        )
        return {
            "total_searches": self.performance_metrics["total_tasks"],
            "successful_searches": successful_searches,
            "failed_searches": self.performance_metrics["failed_tasks"],
            "avg_search_time": self.performance_metrics["avg_response_time"],
            "success_rate": self.performance_metrics["success_rate"],
        }
