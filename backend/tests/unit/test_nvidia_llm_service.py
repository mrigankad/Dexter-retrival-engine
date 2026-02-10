"""
Unit tests for NVIDIA LLM Service.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.nvidia_llm_service import NvidiaLLMService


class TestNvidiaLLMService:
    """Tests for NvidiaLLMService."""
    
    @pytest.fixture
    def llm_service(self) -> NvidiaLLMService:
        """Create LLM service instance."""
        return NvidiaLLMService(
            api_key="test-api-key",
            base_url="https://test.api.nvidia.com/v1",
            model="test-model",
        )
    
    @pytest.mark.asyncio
    async def test_generate_success(
        self,
        llm_service: NvidiaLLMService,
        mock_nvidia_response: dict,
    ):
        """Test successful text generation."""
        with patch.object(llm_service, "_get_client") as mock_get_client:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_nvidia_response
            mock_response.raise_for_status = MagicMock()
            
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            
            mock_get_client.return_value = mock_client
            
            result = await llm_service.generate("Test prompt")
            
            assert result == "This is a mock response from NVIDIA NIM."
            mock_client.post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_with_system_prompt(
        self,
        llm_service: NvidiaLLMService,
        mock_nvidia_response: dict,
    ):
        """Test generation with system prompt."""
        with patch.object(llm_service, "_get_client") as mock_get_client:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_nvidia_response
            mock_response.raise_for_status = MagicMock()
            
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            
            mock_get_client.return_value = mock_client
            
            result = await llm_service.generate(
                prompt="Test prompt",
                system_prompt="You are a helpful assistant.",
            )
            
            assert result is not None
            
            # Verify system prompt was included
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert len(payload["messages"]) == 2
            assert payload["messages"][0]["role"] == "system"
    
    def test_service_initialization(self):
        """Test service initialization with custom params."""
        service = NvidiaLLMService(
            api_key="custom-key",
            base_url="https://custom.url",
            model="custom-model",
        )
        
        assert service.api_key == "custom-key"
        assert service.base_url == "https://custom.url"
        assert service.model == "custom-model"
