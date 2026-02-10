"""
Query Router - Classifies queries for pipeline routing.

Uses NVIDIA LLM for intelligent classification of queries into:
- DIRECT_LLM: Direct response without retrieval
- RAG_PIPELINE: Requires document retrieval
- TOOL_PIPELINE: Requires tool execution (future)
"""

from enum import Enum
from typing import Optional, Tuple
import json

from core.config import settings
from core.logger import get_logger, log_timing
from services.nvidia_llm_service import NvidiaLLMService

logger = get_logger(__name__)


class RouteType(str, Enum):
    """Query route types."""
    DIRECT_LLM = "direct_llm"
    RAG_PIPELINE = "rag_pipeline"
    TOOL_PIPELINE = "tool_pipeline"


ROUTING_PROMPT = """You are a query router for a RAG system. Classify the user's query into one of these categories:

1. DIRECT_LLM - Use for:
   - General knowledge questions
   - Conversational responses (greetings, thanks)
   - Creative writing requests
   - Questions about common topics that don't need specific documents

2. RAG_PIPELINE - Use for:
   - Questions requiring specific document knowledge
   - Queries about uploaded documents or files
   - Technical questions needing precise information
   - Any query mentioning "document", "file", "uploaded", or specific content

3. TOOL_PIPELINE - Use for:
   - Requests to perform actions (calculate, search web, etc.)
   - Currently returns as DIRECT_LLM as tools are not yet implemented

Respond with ONLY a JSON object:
{"route": "DIRECT_LLM" | "RAG_PIPELINE", "confidence": 0.0-1.0, "reason": "brief explanation"}

User Query: {query}"""


class QueryRouter:
    """Intelligent query routing using LLM classification."""
    
    def __init__(self, llm_service: Optional[NvidiaLLMService] = None):
        self.llm = llm_service or NvidiaLLMService()
    
    @log_timing("query_routing")
    async def route(self, query: str) -> Tuple[RouteType, float, str]:
        """
        Route a query to the appropriate pipeline.
        
        Args:
            query: User query to classify
            
        Returns:
            Tuple of (route_type, confidence, reason)
        """
        try:
            prompt = ROUTING_PROMPT.format(query=query)
            
            response = await self.llm.generate(
                prompt=prompt,
                max_tokens=100,
                temperature=0.1,  # Low temperature for consistent classification
            )
            
            # Parse JSON response
            result = json.loads(response.strip())
            route_str = result.get("route", "DIRECT_LLM").upper()
            confidence = float(result.get("confidence", 0.7))
            reason = result.get("reason", "")
            
            # Map to enum
            if route_str == "RAG_PIPELINE":
                route = RouteType.RAG_PIPELINE
            elif route_str == "TOOL_PIPELINE":
                route = RouteType.DIRECT_LLM  # Fallback until tools implemented
            else:
                route = RouteType.DIRECT_LLM
            
            logger.info(
                "Query routed",
                route=route.value,
                confidence=confidence,
                reason=reason,
            )
            
            return route, confidence, reason
            
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Routing parse error, defaulting to RAG", error=str(e))
            return RouteType.RAG_PIPELINE, 0.5, "Parse error, defaulting to RAG"
        except Exception as e:
            logger.exception("Routing error", error=str(e))
            return RouteType.RAG_PIPELINE, 0.5, "Error, defaulting to RAG"
    
    async def route_simple(self, query: str) -> RouteType:
        """
        Simple rule-based routing (faster, no LLM call).
        
        Use when LLM routing is too slow or for simple cases.
        """
        query_lower = query.lower()
        
        # Keywords suggesting RAG retrieval
        rag_keywords = [
            "document", "file", "uploaded", "according to",
            "based on", "find in", "search for", "what does",
            "tell me about", "explain from",
        ]
        
        # Keywords suggesting direct LLM
        direct_keywords = [
            "hello", "hi", "thanks", "thank you",
            "how are you", "what is your name",
        ]
        
        for keyword in direct_keywords:
            if keyword in query_lower:
                return RouteType.DIRECT_LLM
        
        for keyword in rag_keywords:
            if keyword in query_lower:
                return RouteType.RAG_PIPELINE
        
        # Default to RAG for unknown queries (safer)
        return RouteType.RAG_PIPELINE
