"""Unit tests for SearchAgent"""

import pytest
from unittest.mock import AsyncMock, patch
from src.agents.core.search_agent import SearchAgent

# Re-export approx for use in tests
approx = pytest.approx


@pytest.fixture
def search_agent():
    agent = SearchAgent()
    return agent


@pytest.fixture
async def initialized_search_agent(search_agent):
    await search_agent.initialize_memory()
    return search_agent


# ── Agent properties ──────────────────────────────────────────────────────────

def test_search_agent_has_correct_name_and_role(search_agent):
    assert search_agent.name == "SearchAgent"
    assert search_agent.role == "Information Retrieval Specialist"


def test_search_agent_inherits_from_agent(search_agent):
    assert hasattr(search_agent, "memory")
    assert hasattr(search_agent, "execute")
    assert hasattr(search_agent, "performance_metrics")


# ── Think method ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_think_returns_strategy_dict(search_agent):
    strategy = await search_agent.think("simple query")
    assert isinstance(strategy, dict)
    assert "use_semantic_search" in strategy
    assert "use_keyword_search" in strategy
    assert "top_k" in strategy


@pytest.mark.asyncio
async def test_think_adjusts_top_k_for_long_queries(search_agent):
    short = await search_agent.think("short")
    long = await search_agent.think("this is a very long query with many words in it")
    # Longer query should have higher top_k
    assert long["top_k"] >= short["top_k"]


# ── Execute - success case ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_retrieves_documents(initialized_search_agent):
    """Test that execute calls retrieval service correctly."""

    # Mock the retrieval service
    mock_docs = [
        {"id": "1", "content": "Document about AI", "score": 0.95},
        {"id": "2", "content": "Another AI doc", "score": 0.87},
    ]

    with patch("src.services.retrieval_service.RetrievalService") as MockRetrievalService:
        mock_instance = AsyncMock()
        mock_instance.retrieve = AsyncMock(return_value={
            "documents": mock_docs,
            "scores": [0.95, 0.87],
        })
        MockRetrievalService.return_value = mock_instance

        result = await initialized_search_agent.execute({
            "task": "retrieve_documents",
            "query": "What is AI?",
            "top_k": 12,
        })

        # Verify result structure
        assert result["status"] == "success"
        assert len(result["documents"]) == 2
        assert result["document_count"] == 2
        assert result["query"] == "What is AI?"
        assert "execution_time" in result

        # Verify retrieval service was called with correct args
        mock_instance.retrieve.assert_called_once()
        call_args = mock_instance.retrieve.call_args
        assert call_args.kwargs["query"] == "What is AI?"
        assert call_args.kwargs["top_k"] == 12


@pytest.mark.asyncio
async def test_execute_respects_top_k(initialized_search_agent):
    """Test that top_k parameter is passed through."""

    mock_docs = [{"id": str(i), "content": f"Doc {i}", "score": 0.9} for i in range(5)]

    with patch("src.services.retrieval_service.RetrievalService") as MockRetrievalService:
        mock_instance = AsyncMock()
        mock_instance.retrieve = AsyncMock(return_value={
            "documents": mock_docs,
            "scores": [0.9] * 5,
        })

        MockRetrievalService.return_value = mock_instance

        await initialized_search_agent.execute({
            "task": "retrieve_documents",
            "query": "test",
            "top_k": 5,
        })

        call_args = mock_instance.retrieve.call_args
        assert call_args.kwargs["top_k"] == 5


@pytest.mark.asyncio
async def test_execute_uses_default_top_k(initialized_search_agent):
    """Test default top_k value."""

    with patch("src.services.retrieval_service.RetrievalService") as MockRetrievalService:
        mock_instance = AsyncMock()
        mock_instance.retrieve = AsyncMock(return_value={
            "documents": [],
            "scores": [],
        })
        MockRetrievalService.return_value = mock_instance

        await initialized_search_agent.execute({
            "task": "retrieve_documents",
            "query": "test",
            # top_k not provided
        })
        call_args = mock_instance.retrieve.call_args
        assert call_args.kwargs["top_k"] == 12  # Default


# ── Execute - failure cases ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_raises_on_wrong_task(initialized_search_agent):
    """Test that SearchAgent only handles retrieve_documents task."""

    with pytest.raises(ValueError, match="only handles 'retrieve_documents'"):
        await initialized_search_agent.execute({
            "task": "wrong_task",
            "query": "test",
        })


@pytest.mark.asyncio
async def test_execute_raises_on_empty_query(initialized_search_agent):
    """Test that empty query is rejected."""

    with pytest.raises(ValueError, match="Query cannot be empty"):
        await initialized_search_agent.execute({
            "task": "retrieve_documents",
            "query": "",
        })


@pytest.mark.asyncio
async def test_execute_raises_on_no_query(initialized_search_agent):
    """Test that missing query is rejected."""

    with pytest.raises(ValueError, match="Query cannot be empty"):
        await initialized_search_agent.execute({
            "task": "retrieve_documents",
            # query not provided
        })


@pytest.mark.asyncio
async def test_execute_propagates_retrieval_errors(initialized_search_agent):
    """Test that errors from retrieval service are propagated."""

    with patch("src.services.retrieval_service.RetrievalService") as MockRetrievalService:
        mock_instance = AsyncMock()
        mock_instance.retrieve = AsyncMock(
            side_effect=RuntimeError("Connection failed")
        )
        MockRetrievalService.return_value = mock_instance

        with pytest.raises(RuntimeError, match="Connection failed"):
            await initialized_search_agent.execute({
                "task": "retrieve_documents",
                "query": "test",
            })


# ── Performance tracking ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_updates_performance_on_success(initialized_search_agent):
    """Test that successful execution updates metrics."""

    with patch("src.services.retrieval_service.RetrievalService") as MockRetrievalService:
        mock_instance = AsyncMock()
        mock_instance.retrieve = AsyncMock(return_value={
            "documents": [{"id": "1"}],
            "scores": [0.95],
        })
        MockRetrievalService.return_value = mock_instance

        assert initialized_search_agent.performance_metrics["total_tasks"] == 0

        await initialized_search_agent.execute({
            "task": "retrieve_documents",
            "query": "test",
        })

        assert initialized_search_agent.performance_metrics["total_tasks"] == 1
        assert initialized_search_agent.performance_metrics["successful_tasks"] == 1
        assert initialized_search_agent.performance_metrics["success_rate"] == 1.0


@pytest.mark.asyncio
async def test_execute_updates_performance_on_failure(initialized_search_agent):
    """Test that failed execution updates metrics."""

    with patch("src.services.retrieval_service.RetrievalService") as MockRetrievalService:
        mock_instance = AsyncMock()
        mock_instance.retrieve = AsyncMock(side_effect=RuntimeError("Error"))
        MockRetrievalService.return_value = mock_instance

        with pytest.raises(RuntimeError):
            await initialized_search_agent.execute({
                "task": "retrieve_documents",
                "query": "test",
            })

        assert initialized_search_agent.performance_metrics["total_tasks"] == 1
        assert initialized_search_agent.performance_metrics["failed_tasks"] == 1
        assert initialized_search_agent.performance_metrics["success_rate"] == 0.0


# ── Memory recording ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_stores_in_memory(initialized_search_agent):
    """Test that successful searches are stored in memory."""

    with patch("src.services.retrieval_service.RetrievalService") as MockRetrievalService:
        mock_instance = AsyncMock()
        mock_instance.retrieve = AsyncMock(return_value={
            "documents": [{"id": "1"}],
            "scores": [0.95],
        })
        MockRetrievalService.return_value = mock_instance

        await initialized_search_agent.execute({
            "task": "retrieve_documents",
            "query": "test query",
        })

        # Check memory
        assert len(initialized_search_agent.memory.short_term) > 0
        entry = initialized_search_agent.memory.short_term[0]
        assert entry["type"] == "search_execution"
        assert entry["query"] == "test query"


# ── Execution history ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_records_in_history(initialized_search_agent):
    """Test that execution is recorded in history."""

    with patch("src.services.retrieval_service.RetrievalService") as MockRetrievalService:
        mock_instance = AsyncMock()
        mock_instance.retrieve = AsyncMock(return_value={
            "documents": [],
            "scores": [],
        })
        MockRetrievalService.return_value = mock_instance

        assert len(initialized_search_agent.execution_history) == 0

        await initialized_search_agent.execute({
            "task": "retrieve_documents",
            "query": "test",
        })

        assert len(initialized_search_agent.execution_history) == 1
        entry = initialized_search_agent.execution_history[0]
        assert entry["task_name"] == "retrieve_documents"
        assert entry["status"] == "success"


# ── Statistics ────────────────────────────────────────────────────────────────

def test_get_search_stats(search_agent):
    """Test search statistics method."""

    # Record some executions
    search_agent.record_execution("retrieve_documents", "success", 1.0)
    search_agent.record_execution("retrieve_documents", "success", 1.2)
    search_agent.record_execution("retrieve_documents", "error", 0.5)

    # Update metrics
    search_agent.update_performance(True,  0.9, 1.0)
    search_agent.update_performance(True,  0.85, 1.2)
    search_agent.update_performance(False, 0.0, 0.5)

    stats = search_agent.get_search_stats()

    assert stats["total_searches"] == 3
    assert stats["successful_searches"] == 2
    assert stats["failed_searches"] == 1
    assert stats["avg_search_time"] == pytest.approx((1.0 + 1.2 + 0.5) / 3)
    assert stats["success_rate"] == pytest.approx(2 / 3)


# ── Integration test ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_multiple_sequential_searches(initialized_search_agent):
    """Test that agent can handle multiple searches sequentially."""

    with patch("src.services.retrieval_service.RetrievalService") as MockRetrievalService:
        mock_instance = AsyncMock()
        mock_instance.retrieve = AsyncMock(return_value={
            "documents": [{"id": "1"}],
            "scores": [0.9],
        })
        MockRetrievalService.return_value = mock_instance

        # Execute multiple searches
        for i in range(3):
            await initialized_search_agent.execute({
                "task": "retrieve_documents",
                "query": f"query {i}",
            })

        # Verify metrics
        assert initialized_search_agent.performance_metrics["total_tasks"] == 3
        assert initialized_search_agent.performance_metrics["success_rate"] == 1.0
        assert len(initialized_search_agent.execution_history) == 3
