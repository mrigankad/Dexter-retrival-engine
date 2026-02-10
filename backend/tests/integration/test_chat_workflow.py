"""
Integration tests for Chat Workflow.
"""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient

from main import app


class TestChatWorkflow:
    """Integration tests for the chat workflow."""
    
    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Test health check endpoint."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            with patch("api.health_routes.get_redis") as mock_redis:
                mock_redis_client = AsyncMock()
                mock_redis_client.ping = AsyncMock(return_value=True)
                mock_redis.return_value = mock_redis_client
                
                response = await client.get("/health/live")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "alive"
    
    @pytest.mark.asyncio
    async def test_root_endpoint(self):
        """Test root endpoint."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/")
            
            assert response.status_code == 200
            data = response.json()
            assert "name" in data
            assert "version" in data
    
    @pytest.mark.asyncio
    async def test_chat_endpoint_requires_query(self):
        """Test chat endpoint validates input."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post("/chat", json={})
            
            assert response.status_code == 422  # Validation error
