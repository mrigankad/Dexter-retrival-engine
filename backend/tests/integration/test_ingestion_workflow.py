"""
Integration tests for Ingestion Workflow.
"""

import pytest
import os
import tempfile
from unittest.mock import AsyncMock, patch

from ingestion.chunking_strategy import ChunkingStrategy
from ingestion.embedding_pipeline import EmbeddingPipeline


class TestChunkingStrategy:
    """Tests for document chunking."""
    
    def test_chunk_text_basic(self, sample_document_text: str):
        """Test basic text chunking."""
        chunker = ChunkingStrategy(chunk_size=50, chunk_overlap=10)
        
        chunks = chunker.chunk_text(sample_document_text)
        
        assert len(chunks) > 0
        assert all("content" in chunk for chunk in chunks)
        assert all("chunk_index" in chunk for chunk in chunks)
    
    def test_chunk_text_with_metadata(self, sample_document_text: str):
        """Test chunking with metadata preservation."""
        chunker = ChunkingStrategy(chunk_size=100, chunk_overlap=20)
        metadata = {"document_id": "test_123", "source": "test.pdf"}
        
        chunks = chunker.chunk_text(sample_document_text, metadata)
        
        assert all(chunk.get("document_id") == "test_123" for chunk in chunks)
        assert all(chunk.get("source") == "test.pdf" for chunk in chunks)
    
    def test_chunk_indices_sequential(self, sample_document_text: str):
        """Test that chunk indices are sequential."""
        chunker = ChunkingStrategy(chunk_size=50, chunk_overlap=10)
        
        chunks = chunker.chunk_text(sample_document_text)
        
        indices = [chunk["chunk_index"] for chunk in chunks]
        assert indices == list(range(len(chunks)))


class TestEmbeddingPipeline:
    """Tests for embedding pipeline."""
    
    @pytest.fixture
    def pipeline(self) -> EmbeddingPipeline:
        """Create pipeline with mocked services."""
        pipeline = EmbeddingPipeline()
        pipeline.parser.parse = AsyncMock(return_value="Test document content")
        pipeline.embedding_service.embed_texts = AsyncMock(
            return_value=[[0.1] * 1024]
        )
        pipeline.vector_store.upsert = AsyncMock(return_value=["vec_123"])
        return pipeline
    
    @pytest.mark.asyncio
    async def test_process_document(self, pipeline: EmbeddingPipeline):
        """Test full document processing."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"Test content")
            temp_path = f.name
        
        try:
            result = await pipeline.process_document(
                document_id="doc_123",
                file_path=temp_path,
            )
            
            assert result["status"] == "success"
            assert result["document_id"] == "doc_123"
            assert result["chunks_count"] >= 1
        finally:
            os.unlink(temp_path)
