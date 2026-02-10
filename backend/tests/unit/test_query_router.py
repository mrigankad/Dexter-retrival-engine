"""
Unit tests for Query Router.
"""

import pytest
from unittest.mock import AsyncMock, patch

from workflow.query_router import QueryRouter,RouteType


class TestQueryRouter:
    """Tests for QueryRouter."""
    
    @pytest.fixture
    def router(self) -> QueryRouter:
        """Create router instance with mocked LLM."""
        mock_llm = AsyncMock()
        return QueryRouter(llm_service=mock_llm)
    
    @pytest.mark.asyncio
    async def test_route_rag_pipeline(self, router: QueryRouter):
        """Test routing to RAG pipeline."""
        router.llm.generate = AsyncMock(return_value='{"route": "RAG_PIPELINE", "confidence": 0.9, "reason": "Query requires document context"}')
        
        route, confidence, reason = await router.route("What does the document say about X?")
        
        assert route == RouteType.RAG_PIPELINE
        assert confidence == 0.9
    
    @pytest.mark.asyncio
    async def test_route_direct_llm(self, router: QueryRouter):
        """Test routing to direct LLM."""
        router.llm.generate = AsyncMock(return_value='{"route": "DIRECT_LLM", "confidence": 0.95, "reason": "General question"}')
        
        route, confidence, reason = await router.route("What is the capital of France?")
        
        assert route == RouteType.DIRECT_LLM
        assert confidence == 0.95
    
    @pytest.mark.asyncio
    async def test_route_fallback_on_error(self, router: QueryRouter):
        """Test fallback to RAG on parse error."""
        router.llm.generate = AsyncMock(return_value="Invalid JSON response")
        
        route, confidence, reason = await router.route("Test query")
        
        # Should fallback to RAG
        assert route == RouteType.RAG_PIPELINE
        assert confidence == 0.5
    
    @pytest.mark.asyncio
    async def test_route_simple_direct(self, router: QueryRouter):
        """Test simple rule-based routing for greetings."""
        route = await router.route_simple("Hello, how are you?")
        
        assert route == RouteType.DIRECT_LLM
    
    @pytest.mark.asyncio
    async def test_route_simple_rag(self, router: QueryRouter):
        """Test simple rule-based routing for document queries."""
        route = await router.route_simple("What does the document say about machine learning?")
        
        assert route == RouteType.RAG_PIPELINE
