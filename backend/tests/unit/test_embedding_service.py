"""
Unit tests for Embedding Service.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.embedding_service import EmbeddingService


class TestEmbeddingService:
    """Tests for EmbeddingService."""
    
    @pytest.fixture
    def embedding_service(self) -> EmbeddingService:
        """Create embedding service instance."""
        return EmbeddingService(
            api_key="test-api-key",
            base_url="https://test.api.nvidia.com/v1",
            model="test-embed-model",
        )
    
    @pytest.mark.asyncio
    async def test_embed_text_success(
        self,
        embedding_service: EmbeddingService,
        mock_embedding_response: dict,
    ):
        """Test successful text embedding."""
        with patch.object(embedding_service, "_get_client") as mock_get_client:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_embedding_response
            mock_response.raise_for_status = MagicMock()
            
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            
            mock_get_client.return_value = mock_client
            
            result = await embedding_service.embed_text("Test text", use_cache=False)
            
            assert len(result) == 1024
            assert all(isinstance(v, float) for v in result)
    
    @pytest.mark.asyncio
    async def test_embed_text_with_cache(
        self,
        embedding_service: EmbeddingService,
        mock_embedding_response: dict,
    ):
        """Test embedding caching."""
        with patch.object(embedding_service, "_get_client") as mock_get_client:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_embedding_response
            mock_response.raise_for_status = MagicMock()
            
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            
            mock_get_client.return_value = mock_client
            
            # First call - should hit API
            result1 = await embedding_service.embed_text("Test text", use_cache=True)
            
            # Second call - should use cache
            result2 = await embedding_service.embed_text("Test text", use_cache=True)
            
            assert result1 == result2
            # Only one API call due to caching
            assert mock_client.post.call_count == 1
    
    def test_clear_cache(self, embedding_service: EmbeddingService):
        """Test cache clearing."""
        embedding_service._cache["test_key"] = [0.1] * 1024
        
        embedding_service.clear_cache()
        
        assert len(embedding_service._cache) == 0
