"""Unit tests for CoordinatorAgent"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.agents.coordinator.coordinator_agent import CoordinatorAgent


@pytest.fixture
def coordinator_agent():
    agent = CoordinatorAgent()
    return agent


@pytest.fixture
async def initialized_coordinator_agent(coordinator_agent):
    await coordinator_agent.initialize()
    return coordinator_agent


# ── Agent properties ──────────────────────────────────────────────────────────

def test_coordinator_agent_has_correct_name_and_role(coordinator_agent):
    assert coordinator_agent.name == "CoordinatorAgent"
    assert coordinator_agent.role == "Workflow Orchestration Specialist"


def test_coordinator_agent_inherits_from_agent(coordinator_agent):
    assert hasattr(coordinator_agent, "memory")
    assert hasattr(coordinator_agent, "execute")
    assert hasattr(coordinator_agent, "performance_metrics")


def test_coordinator_agent_initializes_sub_agents(coordinator_agent):
    assert coordinator_agent.search_agent is not None
    assert coordinator_agent.analysis_agent is not None
    assert coordinator_agent.verification_agent is not None
    assert coordinator_agent.synthesis_agent is not None
    assert len(coordinator_agent.agents) == 4


# ── Think method ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_think_returns_strategy_dict(coordinator_agent):
    strategy = await coordinator_agent.think("test query")
    assert isinstance(strategy, dict)
    assert "execute_full_pipeline" in strategy
    assert "agents_to_use" in strategy
    assert "fallback_strategy" in strategy


@pytest.mark.asyncio
async def test_think_includes_all_agents(coordinator_agent):
    strategy = await coordinator_agent.think("test query")
    expected_agents = ["search", "analysis", "verification", "synthesis"]
    assert strategy["agents_to_use"] == expected_agents


@pytest.mark.asyncio
async def test_think_adjusts_strategy_for_short_query(coordinator_agent):
    strategy = await coordinator_agent.think("hi")  # Very short query
    assert strategy["error_recovery"] == "abort_pipeline"


# ── Execute - success case ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_completes_full_pipeline(initialized_coordinator_agent):
    """Test that execute orchestrates all 4 agents successfully."""

    with patch.object(initialized_coordinator_agent.search_agent, "execute", new_callable=AsyncMock) as mock_search, \
         patch.object(initialized_coordinator_agent.analysis_agent, "execute", new_callable=AsyncMock) as mock_analysis, \
         patch.object(initialized_coordinator_agent.verification_agent, "execute", new_callable=AsyncMock) as mock_verification, \
         patch.object(initialized_coordinator_agent.synthesis_agent, "execute", new_callable=AsyncMock) as mock_synthesis:

        mock_search.return_value = {
            "status": "success",
            "documents": [{"id": "1", "content": "doc1"}, {"id": "2", "content": "doc2"}],
            "scores": [0.95, 0.87],
            "execution_time": 1.0,
        }

        mock_analysis.return_value = {
            "status": "success",
            "key_findings": ["Finding 1", "Finding 2"],
            "patterns": ["Pattern A"],
            "insights": ["Insight X"],
            "execution_time": 2.0,
        }

        mock_verification.return_value = {
            "status": "success",
            "verified": True,
            "confidence_score": 0.9,
            "execution_time": 1.5,
            "verification": {"verified": True, "confidence_score": 0.9},
        }

        mock_synthesis.return_value = {
            "status": "success",
            "response": "Comprehensive answer",
            "confidence_score": 0.87,
            "sources": [{"id": "1", "title": "Doc 1"}],
            "reasoning_trace": ["Step 1", "Step 2"],
            "limitations": [],
            "execution_time": 1.5,
        }

        result = await initialized_coordinator_agent.execute({
            "task": "answer_query",
            "query": "What is AI?",
            "top_k": 12,
        })

        # Verify result structure
        assert result["status"] == "success"
        assert result["query"] == "What is AI?"
        assert "response" in result
        assert "confidence_score" in result
        assert "sources" in result
        assert "pipeline_results" in result
        assert "execution_time" in result

        # Verify all agents were called
        mock_search.assert_called_once()
        mock_analysis.assert_called_once()
        mock_verification.assert_called_once()
        mock_synthesis.assert_called_once()

        # Verify pipeline results
        assert result["pipeline_results"]["search"]["documents_found"] == 2
        assert result["pipeline_results"]["analysis"]["findings_count"] == 2
        assert result["pipeline_results"]["verification"]["verified"] is True


# ── Execute - failure cases ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_raises_on_wrong_task(initialized_coordinator_agent):
    """Test that only answer_query task is accepted."""

    with pytest.raises(ValueError, match="only handles 'answer_query'"):
        await initialized_coordinator_agent.execute({
            "task": "wrong_task",
            "query": "test",
        })


@pytest.mark.asyncio
async def test_execute_requires_query(initialized_coordinator_agent):
    """Test that query is required."""

    with pytest.raises(ValueError, match="No query provided"):
        await initialized_coordinator_agent.execute({
            "task": "answer_query",
            "query": "",
        })


@pytest.mark.asyncio
async def test_execute_stops_on_search_failure(initialized_coordinator_agent):
    """Test that pipeline stops if search fails."""

    with patch.object(initialized_coordinator_agent.search_agent, "execute", new_callable=AsyncMock) as mock_search, \
         patch.object(initialized_coordinator_agent.analysis_agent, "execute", new_callable=AsyncMock) as mock_analysis:

        mock_search.return_value = {
            "status": "error",
            "error": "Search failed",
        }

        with pytest.raises(RuntimeError, match="Search failed"):
            await initialized_coordinator_agent.execute({
                "task": "answer_query",
                "query": "test query",
            })

        # Verify analysis was NOT called (pipeline stopped)
        mock_analysis.assert_not_called()


@pytest.mark.asyncio
async def test_execute_stops_on_analysis_failure(initialized_coordinator_agent):
    """Test that pipeline stops if analysis fails."""

    with patch.object(initialized_coordinator_agent.search_agent, "execute", new_callable=AsyncMock) as mock_search, \
         patch.object(initialized_coordinator_agent.analysis_agent, "execute", new_callable=AsyncMock) as mock_analysis, \
         patch.object(initialized_coordinator_agent.verification_agent, "execute", new_callable=AsyncMock) as mock_verification:

        mock_search.return_value = {
            "status": "success",
            "documents": [{"id": "1", "content": "doc"}],
            "scores": [0.9],
            "execution_time": 1.0,
        }

        mock_analysis.return_value = {
            "status": "error",
            "error": "Analysis failed",
        }

        with pytest.raises(RuntimeError, match="Analysis failed"):
            await initialized_coordinator_agent.execute({
                "task": "answer_query",
                "query": "test query",
            })

        # Verify verification was NOT called
        mock_verification.assert_not_called()


@pytest.mark.asyncio
async def test_execute_stops_on_verification_failure(initialized_coordinator_agent):
    """Test that pipeline stops if verification fails."""

    with patch.object(initialized_coordinator_agent.search_agent, "execute", new_callable=AsyncMock) as mock_search, \
         patch.object(initialized_coordinator_agent.analysis_agent, "execute", new_callable=AsyncMock) as mock_analysis, \
         patch.object(initialized_coordinator_agent.verification_agent, "execute", new_callable=AsyncMock) as mock_verification, \
         patch.object(initialized_coordinator_agent.synthesis_agent, "execute", new_callable=AsyncMock) as mock_synthesis:

        mock_search.return_value = {
            "status": "success",
            "documents": [{"id": "1", "content": "doc"}],
            "scores": [0.9],
            "execution_time": 1.0,
        }

        mock_analysis.return_value = {
            "status": "success",
            "key_findings": ["F1"],
            "patterns": [],
            "insights": [],
            "execution_time": 2.0,
        }

        mock_verification.return_value = {
            "status": "error",
            "error": "Verification failed",
        }

        with pytest.raises(RuntimeError, match="Verification failed"):
            await initialized_coordinator_agent.execute({
                "task": "answer_query",
                "query": "test query",
            })

        # Verify synthesis was NOT called
        mock_synthesis.assert_not_called()


# ── Performance tracking ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_updates_performance_on_success(initialized_coordinator_agent):
    """Test that successful execution updates metrics."""

    with patch.object(initialized_coordinator_agent.search_agent, "execute", new_callable=AsyncMock) as mock_search, \
         patch.object(initialized_coordinator_agent.analysis_agent, "execute", new_callable=AsyncMock) as mock_analysis, \
         patch.object(initialized_coordinator_agent.verification_agent, "execute", new_callable=AsyncMock) as mock_verification, \
         patch.object(initialized_coordinator_agent.synthesis_agent, "execute", new_callable=AsyncMock) as mock_synthesis:

        mock_search.return_value = {
            "status": "success",
            "documents": [],
            "scores": [],
            "execution_time": 1.0,
        }
        mock_analysis.return_value = {
            "status": "success",
            "key_findings": [],
            "patterns": [],
            "insights": [],
            "execution_time": 1.0,
        }
        mock_verification.return_value = {
            "status": "success",
            "verified": True,
            "confidence_score": 0.8,
            "execution_time": 1.0,
            "verification": {"verified": True, "confidence_score": 0.8},
        }
        mock_synthesis.return_value = {
            "status": "success",
            "response": "Answer",
            "confidence_score": 0.8,
            "sources": [],
            "reasoning_trace": [],
            "limitations": [],
            "execution_time": 1.0,
        }

        assert initialized_coordinator_agent.performance_metrics["total_tasks"] == 0

        await initialized_coordinator_agent.execute({
            "task": "answer_query",
            "query": "test",
        })

        assert initialized_coordinator_agent.performance_metrics["total_tasks"] == 1
        assert initialized_coordinator_agent.performance_metrics["successful_tasks"] == 1


@pytest.mark.asyncio
async def test_execute_updates_performance_on_failure(initialized_coordinator_agent):
    """Test that failed execution updates metrics."""

    with patch.object(initialized_coordinator_agent.search_agent, "execute", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = {"status": "error"}

        with pytest.raises(RuntimeError):
            await initialized_coordinator_agent.execute({
                "task": "answer_query",
                "query": "test",
            })

        assert initialized_coordinator_agent.performance_metrics["total_tasks"] == 1
        assert initialized_coordinator_agent.performance_metrics["failed_tasks"] == 1


# ── Memory recording ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_stores_workflow_in_memory(initialized_coordinator_agent):
    """Test that successful workflow is stored in memory."""

    with patch.object(initialized_coordinator_agent.search_agent, "execute", new_callable=AsyncMock) as mock_search, \
         patch.object(initialized_coordinator_agent.analysis_agent, "execute", new_callable=AsyncMock) as mock_analysis, \
         patch.object(initialized_coordinator_agent.verification_agent, "execute", new_callable=AsyncMock) as mock_verification, \
         patch.object(initialized_coordinator_agent.synthesis_agent, "execute", new_callable=AsyncMock) as mock_synthesis:

        mock_search.return_value = {
            "status": "success",
            "documents": [],
            "scores": [],
            "execution_time": 1.0,
        }
        mock_analysis.return_value = {
            "status": "success",
            "key_findings": [],
            "patterns": [],
            "insights": [],
            "execution_time": 1.0,
        }
        mock_verification.return_value = {
            "status": "success",
            "verified": True,
            "confidence_score": 0.8,
            "execution_time": 1.0,
            "verification": {"verified": True, "confidence_score": 0.8},
        }
        mock_synthesis.return_value = {
            "status": "success",
            "response": "Answer",
            "confidence_score": 0.8,
            "sources": [],
            "reasoning_trace": [],
            "limitations": [],
            "execution_time": 1.0,
        }

        await initialized_coordinator_agent.execute({
            "task": "answer_query",
            "query": "test query",
        })

        assert len(initialized_coordinator_agent.memory.short_term) > 0
        entry = initialized_coordinator_agent.memory.short_term[0]
        assert entry["type"] == "coordination_execution"
        assert entry["query"] == "test query"


# ── Execution history ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_records_in_history(initialized_coordinator_agent):
    """Test that execution is recorded in history."""

    with patch.object(initialized_coordinator_agent.search_agent, "execute", new_callable=AsyncMock) as mock_search, \
         patch.object(initialized_coordinator_agent.analysis_agent, "execute", new_callable=AsyncMock) as mock_analysis, \
         patch.object(initialized_coordinator_agent.verification_agent, "execute", new_callable=AsyncMock) as mock_verification, \
         patch.object(initialized_coordinator_agent.synthesis_agent, "execute", new_callable=AsyncMock) as mock_synthesis:

        mock_search.return_value = {
            "status": "success",
            "documents": [],
            "scores": [],
            "execution_time": 1.0,
        }
        mock_analysis.return_value = {
            "status": "success",
            "key_findings": [],
            "patterns": [],
            "insights": [],
            "execution_time": 1.0,
        }
        mock_verification.return_value = {
            "status": "success",
            "verified": True,
            "confidence_score": 0.8,
            "execution_time": 1.0,
            "verification": {"verified": True, "confidence_score": 0.8},
        }
        mock_synthesis.return_value = {
            "status": "success",
            "response": "Answer",
            "confidence_score": 0.8,
            "sources": [],
            "reasoning_trace": [],
            "limitations": [],
            "execution_time": 1.0,
        }

        assert len(initialized_coordinator_agent.execution_history) == 0

        await initialized_coordinator_agent.execute({
            "task": "answer_query",
            "query": "test",
        })

        assert len(initialized_coordinator_agent.execution_history) == 1
        entry = initialized_coordinator_agent.execution_history[0]
        assert entry["task_name"] == "answer_query"
        assert entry["status"] == "success"


# ── Statistics ────────────────────────────────────────────────────────────────

def test_get_pipeline_stats(coordinator_agent):
    """Test pipeline statistics method."""

    coordinator_agent.record_execution("answer_query", "success", 5.0)
    coordinator_agent.record_execution("answer_query", "success", 6.0)
    coordinator_agent.record_execution("answer_query", "error", 2.0)
    coordinator_agent.update_performance(True, 0.9, 5.0)
    coordinator_agent.update_performance(True, 0.85, 6.0)
    coordinator_agent.update_performance(False, 0.0, 2.0)

    stats = coordinator_agent.get_pipeline_stats()

    assert stats["total_workflows"] == 3
    assert stats["successful_workflows"] == 2
    assert stats["failed_workflows"] == 1
    assert "agent_performance" in stats
    assert len(stats["agent_performance"]) == 4  # 4 sub-agents


# ── Pipeline orchestration ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_passes_results_between_agents(initialized_coordinator_agent):
    """Test that results are correctly passed through pipeline."""

    with patch.object(initialized_coordinator_agent.search_agent, "execute", new_callable=AsyncMock) as mock_search, \
         patch.object(initialized_coordinator_agent.analysis_agent, "execute", new_callable=AsyncMock) as mock_analysis, \
         patch.object(initialized_coordinator_agent.verification_agent, "execute", new_callable=AsyncMock) as mock_verification, \
         patch.object(initialized_coordinator_agent.synthesis_agent, "execute", new_callable=AsyncMock) as mock_synthesis:

        mock_search.return_value = {
            "status": "success",
            "documents": [{"id": "1", "content": "test doc"}],
            "scores": [0.95],
            "execution_time": 1.0,
        }
        mock_analysis.return_value = {
            "status": "success",
            "key_findings": ["F1", "F2"],
            "patterns": ["P1"],
            "insights": ["I1"],
            "execution_time": 2.0,
        }
        mock_verification.return_value = {
            "status": "success",
            "verified": True,
            "confidence_score": 0.85,
            "execution_time": 1.5,
            "verification": {"verified": True, "confidence_score": 0.85},
        }
        mock_synthesis.return_value = {
            "status": "success",
            "response": "Answer",
            "confidence_score": 0.85,
            "sources": [{"id": "1", "title": "test doc"}],
            "reasoning_trace": ["Trace"],
            "limitations": [],
            "execution_time": 1.5,
        }

        await initialized_coordinator_agent.execute({
            "task": "answer_query",
            "query": "test",
        })

        # Verify search was called with query
        search_call = mock_search.call_args
        assert search_call[0][0]["query"] == "test"

        # Verify analysis received search results
        analysis_call = mock_analysis.call_args
        assert "previous_results" in analysis_call[0][0]
        assert "documents" in analysis_call[0][0]["previous_results"]

        # Verify verification received analysis results
        verification_call = mock_verification.call_args
        assert "previous_results" in verification_call[0][0]
        assert "key_findings" in verification_call[0][0]["previous_results"]

        # Verify synthesis received all prior results
        synthesis_call = mock_synthesis.call_args
        assert "previous_results" in synthesis_call[0][0]
        assert "search_results" in synthesis_call[0][0]["previous_results"]
        assert "analysis_results" in synthesis_call[0][0]["previous_results"]
        assert "verification_results" in synthesis_call[0][0]["previous_results"]


# ── Integration test ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_multiple_sequential_workflows(initialized_coordinator_agent):
    """Test multiple workflow executions."""

    with patch.object(initialized_coordinator_agent.search_agent, "execute", new_callable=AsyncMock) as mock_search, \
         patch.object(initialized_coordinator_agent.analysis_agent, "execute", new_callable=AsyncMock) as mock_analysis, \
         patch.object(initialized_coordinator_agent.verification_agent, "execute", new_callable=AsyncMock) as mock_verification, \
         patch.object(initialized_coordinator_agent.synthesis_agent, "execute", new_callable=AsyncMock) as mock_synthesis:

        mock_search.return_value = {
            "status": "success",
            "documents": [],
            "scores": [],
            "execution_time": 1.0,
        }
        mock_analysis.return_value = {
            "status": "success",
            "key_findings": [],
            "patterns": [],
            "insights": [],
            "execution_time": 1.0,
        }
        mock_verification.return_value = {
            "status": "success",
            "verified": True,
            "confidence_score": 0.8,
            "execution_time": 1.0,
            "verification": {"verified": True, "confidence_score": 0.8},
        }
        mock_synthesis.return_value = {
            "status": "success",
            "response": "Answer",
            "confidence_score": 0.8,
            "sources": [],
            "reasoning_trace": [],
            "limitations": [],
            "execution_time": 1.0,
        }

        for i in range(3):
            await initialized_coordinator_agent.execute({
                "task": "answer_query",
                "query": f"query {i}",
            })

        assert initialized_coordinator_agent.performance_metrics["total_tasks"] == 3
        assert len(initialized_coordinator_agent.execution_history) == 3
        assert mock_search.call_count == 3
        assert mock_analysis.call_count == 3
        assert mock_verification.call_count == 3
        assert mock_synthesis.call_count == 3
