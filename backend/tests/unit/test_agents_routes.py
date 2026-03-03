"""
Integration tests for multi-agent RAG API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from main import app

client = TestClient(app)


# ── Query Endpoint Tests ───────────────────────────────────────────────────────

class TestQueryEndpoint:
    """Tests for POST /api/agents/query endpoint."""

    def test_query_with_valid_request(self):
        """Test successful query execution."""
        with patch("api.agents_routes.coordinator.execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {
                "status": "success",
                "query": "What is AI?",
                "response": "Artificial Intelligence (AI) is...",
                "confidence_score": 0.87,
                "sources": [
                    {
                        "id": "doc_1",
                        "title": "Introduction to AI",
                        "relevance": 0.95,
                        "url": "https://example.com/ai"
                    }
                ],
                "reasoning_trace": ["Step 1", "Step 2"],
                "limitations": [],
                "pipeline_results": {
                    "search": {"documents_found": 12, "execution_time": 1.0},
                    "analysis": {"findings_count": 5, "execution_time": 2.0},
                    "verification": {"verified": True, "confidence": 0.87, "execution_time": 1.5},
                    "synthesis": {"execution_time": 1.5}
                },
                "execution_time": 6.0,
                "metadata": {"pipeline": "search->analysis->verification->synthesis", "agents_used": 4}
            }

            response = client.post(
                "/api/agents/query",
                json={
                    "query": "What is AI?",
                    "top_k": 12
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["query"] == "What is AI?"
            assert "response" in data
            assert "confidence_score" in data
            assert "sources" in data
            assert "pipeline_results" in data

    def test_query_missing_query_field(self):
        """Test query endpoint with missing query field."""
        response = client.post(
            "/api/agents/query",
            json={"top_k": 12}
        )

        assert response.status_code == 422  # Validation error

    def test_query_empty_query(self):
        """Test query endpoint with empty query string."""
        response = client.post(
            "/api/agents/query",
            json={"query": "", "top_k": 12}
        )

        assert response.status_code == 422  # Validation error

    def test_query_invalid_top_k(self):
        """Test query endpoint with invalid top_k value."""
        response = client.post(
            "/api/agents/query",
            json={"query": "test", "top_k": 100}  # Exceeds max of 50
        )

        assert response.status_code == 422  # Validation error

    def test_query_with_default_top_k(self):
        """Test query endpoint with default top_k."""
        with patch("api.agents_routes.coordinator.execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {
                "status": "success",
                "query": "test",
                "response": "answer",
                "confidence_score": 0.8,
                "sources": [],
                "reasoning_trace": [],
                "limitations": [],
                "pipeline_results": {
                    "search": {"documents_found": 0, "execution_time": 1.0},
                    "analysis": {"findings_count": 0, "execution_time": 1.0},
                    "verification": {"verified": True, "confidence": 0.8, "execution_time": 1.0},
                    "synthesis": {"execution_time": 1.0}
                },
                "execution_time": 4.0,
                "metadata": {}
            }

            response = client.post(
                "/api/agents/query",
                json={"query": "test"}  # No top_k specified
            )

            assert response.status_code == 200
            # Verify default top_k was used
            call_args = mock_execute.call_args
            assert call_args[0][0]["top_k"] == 12

    def test_query_pipeline_failure(self):
        """Test query endpoint when pipeline fails."""
        with patch("api.agents_routes.coordinator.execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = RuntimeError("Pipeline failed")

            response = client.post(
                "/api/agents/query",
                json={"query": "test", "top_k": 12}
            )

            assert response.status_code == 500
            assert "error" in response.json() or "detail" in response.json()


# ── Statistics Endpoint Tests ──────────────────────────────────────────────────

class TestStatisticsEndpoint:
    """Tests for GET /api/agents/statistics endpoint."""

    def test_get_statistics(self):
        """Test retrieving pipeline statistics."""
        with patch("api.agents_routes.coordinator.get_pipeline_stats") as mock_stats:
            mock_stats.return_value = {
                "total_workflows": 100,
                "successful_workflows": 95,
                "failed_workflows": 5,
                "avg_workflow_time": 5.2,
                "success_rate": 0.95,
                "agent_performance": {
                    "search": {
                        "total_tasks": 100,
                        "successful_tasks": 100,
                        "success_rate": 1.0
                    },
                    "analysis": {
                        "total_tasks": 95,
                        "successful_tasks": 95,
                        "success_rate": 1.0
                    },
                    "verification": {
                        "total_tasks": 95,
                        "successful_tasks": 95,
                        "success_rate": 1.0
                    },
                    "synthesis": {
                        "total_tasks": 95,
                        "successful_tasks": 95,
                        "success_rate": 1.0
                    }
                }
            }

            response = client.get("/api/agents/statistics")

            assert response.status_code == 200
            data = response.json()
            assert data["total_workflows"] == 100
            assert data["successful_workflows"] == 95
            assert data["success_rate"] == 0.95
            assert "agent_performance" in data
            assert len(data["agent_performance"]) == 4


# ── Health Check Endpoint Tests ────────────────────────────────────────────────

class TestHealthEndpoint:
    """Tests for GET /api/agents/health endpoint."""

    def test_health_check_healthy(self):
        """Test health check when system is healthy."""
        response = client.get("/api/agents/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "agents_ready" in data
        assert "timestamp" in data

    def test_health_check_response_format(self):
        """Test health check response format."""
        response = client.get("/api/agents/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded", "unhealthy"]
        assert isinstance(data["agents_ready"], bool)
        assert isinstance(data["timestamp"], str)


# ── List Agents Endpoint Tests ─────────────────────────────────────────────────

class TestListAgentsEndpoint:
    """Tests for GET /api/agents/agents/list endpoint."""

    def test_list_agents(self):
        """Test listing all agents."""
        response = client.get("/api/agents/agents/list")

        assert response.status_code == 200
        data = response.json()

        # Verify all agents are listed
        expected_agents = ["coordinator", "search", "analysis", "verification", "synthesis"]
        for agent in expected_agents:
            assert agent in data
            assert "name" in data[agent]
            assert "role" in data[agent]
            assert "type" in data[agent]

    def test_list_agents_coordinator_info(self):
        """Test that coordinator agent info is correct."""
        response = client.get("/api/agents/agents/list")

        assert response.status_code == 200
        data = response.json()
        assert data["coordinator"]["name"] == "CoordinatorAgent"
        assert data["coordinator"]["type"] == "orchestrator"

    def test_list_agents_specialized_agents(self):
        """Test that all specialized agents are listed with correct type."""
        response = client.get("/api/agents/agents/list")

        assert response.status_code == 200
        data = response.json()
        specialized = ["search", "analysis", "verification", "synthesis"]
        for agent_name in specialized:
            assert data[agent_name]["type"] == "specialized"


# ── Agent Statistics Endpoint Tests ────────────────────────────────────────────

class TestAgentStatsEndpoint:
    """Tests for GET /api/agents/agents/{agent_name}/stats endpoint."""

    def test_get_search_agent_stats(self):
        """Test retrieving SearchAgent statistics."""
        response = client.get("/api/agents/agents/search/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["agent"] == "search"
        assert data["name"] == "SearchAgent"
        assert "performance" in data
        assert "total_tasks" in data["performance"]
        assert "success_rate" in data["performance"]

    def test_get_all_agent_stats(self):
        """Test retrieving statistics for all agents."""
        agents = ["search", "analysis", "verification", "synthesis"]

        for agent_name in agents:
            response = client.get(f"/api/agents/agents/{agent_name}/stats")
            assert response.status_code == 200
            data = response.json()
            assert data["agent"] == agent_name
            assert "performance" in data

    def test_get_invalid_agent_stats(self):
        """Test retrieving statistics for non-existent agent."""
        response = client.get("/api/agents/agents/invalid/stats")

        assert response.status_code == 404
        assert "error" in response.json() or "detail" in response.json()

    def test_agent_stats_format(self):
        """Test format of agent statistics response."""
        response = client.get("/api/agents/agents/search/stats")

        assert response.status_code == 200
        data = response.json()

        required_fields = ["agent", "name", "role", "performance"]
        for field in required_fields:
            assert field in data

        performance_fields = [
            "total_tasks", "successful_tasks", "failed_tasks",
            "success_rate", "avg_response_time"
        ]
        for field in performance_fields:
            assert field in data["performance"]


# ── Integration Tests ──────────────────────────────────────────────────────────

class TestIntegration:
    """Integration tests for the multi-agent API."""

    def test_full_workflow(self):
        """Test a complete query workflow."""
        with patch("api.agents_routes.coordinator.execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {
                "status": "success",
                "query": "What is machine learning?",
                "response": "Machine learning is...",
                "confidence_score": 0.9,
                "sources": [{"id": "1", "title": "ML Basics", "relevance": 0.95, "url": "http://example.com"}],
                "reasoning_trace": ["Found sources", "Analyzed content", "Verified accuracy", "Synthesized response"],
                "limitations": [],
                "pipeline_results": {
                    "search": {"documents_found": 10, "execution_time": 1.2},
                    "analysis": {"findings_count": 4, "execution_time": 2.1},
                    "verification": {"verified": True, "confidence": 0.9, "execution_time": 1.5},
                    "synthesis": {"execution_time": 1.2}
                },
                "execution_time": 6.0,
                "metadata": {"pipeline": "search->analysis->verification->synthesis", "agents_used": 4}
            }

            # Execute query
            response = client.post(
                "/api/agents/query",
                json={"query": "What is machine learning?", "top_k": 12}
            )

            assert response.status_code == 200
            query_data = response.json()
            assert query_data["status"] == "success"

            # Get statistics
            with patch("api.agents_routes.coordinator.get_pipeline_stats") as mock_stats:
                mock_stats.return_value = {
                    "total_workflows": 1,
                    "successful_workflows": 1,
                    "failed_workflows": 0,
                    "avg_workflow_time": 6.0,
                    "success_rate": 1.0,
                    "agent_performance": {
                        "search": {"total_tasks": 1, "successful_tasks": 1, "success_rate": 1.0},
                        "analysis": {"total_tasks": 1, "successful_tasks": 1, "success_rate": 1.0},
                        "verification": {"total_tasks": 1, "successful_tasks": 1, "success_rate": 1.0},
                        "synthesis": {"total_tasks": 1, "successful_tasks": 1, "success_rate": 1.0}
                    }
                }

                stats_response = client.get("/api/agents/statistics")
                assert stats_response.status_code == 200
                stats_data = stats_response.json()
                assert stats_data["total_workflows"] == 1

    def test_error_handling_consistency(self):
        """Test that errors are handled consistently across endpoints."""
        with patch("api.agents_routes.coordinator.execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = Exception("Unexpected error")

            response = client.post(
                "/api/agents/query",
                json={"query": "test"}
            )

            assert response.status_code == 500
            error_data = response.json()
            assert "error" in error_data or "detail" in error_data
