"""
Retrieval Service.

Enhanced retrieval combining:
- Semantic (embedding-based) search
- Keyword-based filtering for hybrid search
- Reranking for improved relevance
"""

from typing import List, Dict, Any, Optional
import re

from core.config import settings
from core.logger import get_logger, log_timing
from .embedding_service import EmbeddingService
from .vector_store_service import VectorStoreService
from .reranker_service import RerankerService

logger = get_logger(__name__)


class RetrievalService:
    """Enhanced retrieval service with hybrid search for RAG pipeline."""
    
    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.vector_store = VectorStoreService()
        self.reranker = RerankerService()
    
    def _keyword_score(self, text: str, keywords: List[str]) -> float:
        """Calculate keyword match score for a text snippet."""
        if not keywords or not text:
            return 0.0
        
        text_lower = text.lower()
        matches = 0
        total_weight = 0
        
        for keyword in keywords:
            keyword_lower = keyword.lower()
            # Weight multi-word keywords higher
            weight = len(keyword.split())
            total_weight += weight
            
            if keyword_lower in text_lower:
                # Bonus for exact match at word boundary
                pattern = r'\b' + re.escape(keyword_lower) + r'\b'
                if re.search(pattern, text_lower):
                    matches += weight * 1.2  # Extra weight for exact word match
                else:
                    matches += weight
        
        return matches / max(total_weight, 1)
    
    @log_timing("retrieval")
    async def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        rerank: bool = True,
        rerank_top_k: Optional[int] = None,
        filter_conditions: Optional[Dict] = None,
        keywords: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant documents using hybrid search.
        
        Args:
            query: Search query
            top_k: Number of initial results from vector search
            rerank: Whether to rerank results
            rerank_top_k: Number of results after reranking
            filter_conditions: Optional filter conditions
            keywords: Optional keywords for hybrid search scoring
            
        Returns:
            List of relevant documents with metadata
        """
        top_k = top_k or settings.top_k_retrieval
        rerank_top_k = rerank_top_k or settings.rerank_top_k
        
        # Generate query embedding
        query_embedding = await self.embedding_service.embed_query(query)
        
        # Vector search - get more if reranking or using keywords
        search_multiplier = 2 if (rerank or keywords) else 1
        initial_results = await self.vector_store.search(
            query_vector=query_embedding,
            top_k=top_k * search_multiplier,
            filter_conditions=filter_conditions,
        )
        
        if not initial_results:
            logger.info("No results found", query=query[:100])
            return []
        
        results = initial_results
        
        # Apply keyword boost if keywords provided (hybrid scoring)
        if keywords and settings.hybrid_search_enabled:
            keyword_weight = settings.keyword_search_weight
            semantic_weight = 1 - keyword_weight
            
            for result in results:
                content = result.get("payload", {}).get("content", "")
                semantic_score = result.get("score", 0)
                keyword_score = self._keyword_score(content, keywords)
                
                # Combine scores
                result["semantic_score"] = semantic_score
                result["keyword_score"] = keyword_score
                result["score"] = (semantic_weight * semantic_score) + (keyword_weight * keyword_score)
            
            # Re-sort by combined score
            results.sort(key=lambda x: x.get("score", 0), reverse=True)
            
            logger.debug(
                "Hybrid search applied",
                keywords=keywords[:5],
                keyword_weight=keyword_weight,
            )
        
        # Rerank if enabled and we have enough results
        if rerank and settings.enable_reranking and len(results) > 1:
            try:
                documents = [r["payload"].get("content", "") for r in results]
                reranked = await self.reranker.rerank(query, documents, rerank_top_k)
                
                # Map back to full results with rerank scores
                final_results = []
                for idx, _, score in reranked:
                    result = results[idx].copy()
                    result["rerank_score"] = score
                    final_results.append(result)
                
                logger.info(
                    "Reranking complete",
                    input_count=len(results),
                    output_count=len(final_results),
                )
                
                return final_results
            except Exception as e:
                logger.warning(
                    "Reranking failed, using original ranking",
                    error=str(e),
                )
                # Fall through to return un-reranked results
        
        return results[:top_k]
    
    async def retrieve_with_context(
        self,
        query: str,
        top_k: Optional[int] = None,
        max_tokens: int = 4096,
        filter_conditions: Optional[Dict] = None,
        keywords: Optional[List[str]] = None,
    ) -> str:
        """
        Retrieve and format context for LLM.
        
        Args:
            query: Search query
            top_k: Number of results
            max_tokens: Approximate max context length
            filter_conditions: Optional filter conditions (e.g., {"page": 100})
            keywords: Optional keywords for hybrid search
            
        Returns:
            Formatted context string with page references
        """
        # Use reranking from settings
        results = await self.retrieve(
            query, 
            top_k, 
            rerank=settings.enable_reranking,
            filter_conditions=filter_conditions,
            keywords=keywords,
        )
        
        if not results:
            return ""
        
        context_parts = []
        current_length = 0
        seen_content = set()  # Avoid duplicate chunks
        
        for i, result in enumerate(results, 1):
            content = result["payload"].get("content", "")
            
            # Skip if we've already included very similar content
            content_hash = hash(content[:200])  # Use first 200 chars for dedup
            if content_hash in seen_content:
                continue
            seen_content.add(content_hash)
            
            source = result["payload"].get("source", "Unknown")
            page = result["payload"].get("page", "N/A")
            total_pages = result["payload"].get("total_pages", "N/A")
            score = result.get("score", 0)
            rerank_score = result.get("rerank_score")
            
            # Rough token count (4 chars per token)
            content_tokens = len(content) // 4
            if current_length + content_tokens > max_tokens:
                logger.debug(
                    "Context limit reached",
                    included_chunks=len(context_parts),
                    current_tokens=current_length,
                )
                break
            
            # Build source citation with relevance indicator
            score_indicator = ""
            if rerank_score and rerank_score > 0.5:
                score_indicator = " [HIGH RELEVANCE]"
            elif score > 0.8:
                score_indicator = " [HIGH RELEVANCE]"
            
            # Include page number in source citation
            if page != "N/A":
                header = f"[Source {i}: {source}, Page {page}/{total_pages}{score_indicator}]"
            else:
                header = f"[Source {i}: {source}{score_indicator}]"
            
            context_parts.append(f"{header}\n{content}")
            current_length += content_tokens
        
        formatted_context = "\n\n---\n\n".join(context_parts)
        
        logger.info(
            "Context assembled",
            chunks_included=len(context_parts),
            approximate_tokens=current_length,
        )
        
        return formatted_context
