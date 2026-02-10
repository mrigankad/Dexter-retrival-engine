"""
Unit tests for RAG Pipeline.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from workflow.rag_pipeline import RAGPipeline


class TestRAGPipeline:
    """Tests for RAGPipeline."""
    
    @pytest.fixture
    def rag_pipeline(self) -> RAGPipeline:
        """Create RAG pipeline with mocked services."""
        mock_llm = AsyncMock()
        mock_embedding = AsyncMock()
        mock_retrieval = AsyncMock()
        
        return RAGPipeline(
            llm_service=mock_llm,
            embedding_service=mock_embedding,
            retrieval_service=mock_retrieval,
        )
    
    @pytest.mark.asyncio
    async def test_rewrite_query(self, rag_pipeline: RAGPipeline):
        """Test query rewriting."""
        rag_pipeline.llm.generate = AsyncMock(return_value="Rewritten query about topic")
        
        result = await rag_pipeline.rewrite_query("Tell me about topic")
        
        assert result == "Rewritten query about topic"
        rag_pipeline.llm.generate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_with_context(self, rag_pipeline: RAGPipeline):
        """Test full RAG execution with context."""
        rag_pipeline.llm.generate = AsyncMock(
            side_effect=[
                "Rewritten query",  # For query rewriting
                "Response based on context",  # For final generation
            ]
        )
        rag_pipeline.retrieval.retrieve_with_context = AsyncMock(
            return_value="Retrieved context from documents"
        )
        
        result = await rag_pipeline.execute("What is machine learning?")
        
        assert result["response"] == "Response based on context"
        assert result["context_used"] is True
        assert result["query_rewritten"] == "Rewritten query"
    
    @pytest.mark.asyncio
    async def test_execute_without_context(self, rag_pipeline: RAGPipeline):
        """Test RAG execution when no context found."""
        rag_pipeline.llm.generate = AsyncMock(
            side_effect=[
                "Rewritten query",
                "Direct response without context",
            ]
        )
        rag_pipeline.retrieval.retrieve_with_context = AsyncMock(return_value="")
        
        result = await rag_pipeline.execute("Random question")
        
        assert result["context_used"] is False
