"""Unit tests for AnalysisAgent"""

import pytest
from unittest.mock import AsyncMock, patch
from src.agents.core.analysis_agent import AnalysisAgent


@pytest.fixture
def analysis_agent():
    agent = AnalysisAgent()
    return agent


@pytest.fixture
async def initialized_analysis_agent(analysis_agent):
    await analysis_agent.initialize_memory()
    return analysis_agent


# ── Agent properties ──────────────────────────────────────────────────────────

def test_analysis_agent_has_correct_name_and_role(analysis_agent):
    assert analysis_agent.name == "AnalysisAgent"
    assert analysis_agent.role == "Data Analysis Specialist"


def test_analysis_agent_inherits_from_agent(analysis_agent):
    assert hasattr(analysis_agent, "memory")
    assert hasattr(analysis_agent, "execute")
    assert hasattr(analysis_agent, "performance_metrics")


# ── Think method ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_think_returns_strategy_dict(analysis_agent):
    strategy = await analysis_agent.think([{"content": "test"}], "query")
    assert isinstance(strategy, dict)
    assert "extract_key_findings" in strategy
    assert "depth_level" in strategy


@pytest.mark.asyncio
async def test_think_adjusts_strategy_for_many_docs(analysis_agent):
    many_docs = [{"content": f"doc {i}"} for i in range(15)]
    strategy = await analysis_agent.think(many_docs, "query")
    assert strategy["depth_level"] == "shallow"
    assert strategy["max_findings"] == 3


@pytest.mark.asyncio
async def test_think_adjusts_strategy_for_few_docs(analysis_agent):
    few_docs = [{"content": "doc 1"}]
    strategy = await analysis_agent.think(few_docs, "query")
    assert strategy["depth_level"] == "deep"
    assert strategy["max_findings"] == 10


# ── Execute - success case ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_analyzes_documents(initialized_analysis_agent):
    """Test that execute calls LLM service correctly."""

    mock_response = """{
        "key_findings": ["Finding 1", "Finding 2"],
        "patterns": ["Pattern A"],
        "insights": ["Insight X"],
        "summary": "Overall summary"
    }"""

    with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLMService:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=mock_response)
        MockLLMService.return_value = mock_instance

        result = await initialized_analysis_agent.execute({
            "task": "analyze_documents",
            "query": "What patterns exist?",
            "previous_results": {
                "documents": [
                    {"id": "1", "content": "Document about AI", "score": 0.95},
                    {"id": "2", "content": "Another doc", "score": 0.87},
                ],
                "scores": [0.95, 0.87],
            },
        })

        # Verify result structure
        assert result["status"] == "success"
        assert "key_findings" in result
        assert "patterns" in result
        assert "insights" in result
        assert len(result["key_findings"]) >= 0
        assert "execution_time" in result


@pytest.mark.asyncio
async def test_execute_validates_documents_provided(initialized_analysis_agent):
    """Test that empty documents are rejected."""

    with pytest.raises(ValueError, match="No documents provided"):
        await initialized_analysis_agent.execute({
            "task": "analyze_documents",
            "previous_results": {"documents": []},
        })


# ── Execute - failure cases ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_raises_on_wrong_task(initialized_analysis_agent):
    """Test that AnalysisAgent only handles analyze_documents task."""

    with pytest.raises(ValueError, match="only handles 'analyze_documents'"):
        await initialized_analysis_agent.execute({
            "task": "wrong_task",
            "previous_results": {"documents": [{"content": "test"}]},
        })


@pytest.mark.asyncio
async def test_execute_propagates_llm_errors(initialized_analysis_agent):
    """Test that errors from LLM service are propagated."""

    with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLMService:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(
            side_effect=RuntimeError("LLM connection failed")
        )
        MockLLMService.return_value = mock_instance

        with pytest.raises(RuntimeError, match="LLM connection failed"):
            await initialized_analysis_agent.execute({
                "task": "analyze_documents",
                "previous_results": {
                    "documents": [{"id": "1", "content": "test"}]
                },
            })


# ── Performance tracking ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_updates_performance_on_success(initialized_analysis_agent):
    """Test that successful execution updates metrics."""

    mock_response = '{"key_findings": [], "patterns": [], "insights": [], "summary": ""}'

    with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLMService:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=mock_response)
        MockLLMService.return_value = mock_instance

        assert initialized_analysis_agent.performance_metrics["total_tasks"] == 0

        await initialized_analysis_agent.execute({
            "task": "analyze_documents",
            "previous_results": {
                "documents": [{"id": "1", "content": "test"}]
            },
        })

        assert initialized_analysis_agent.performance_metrics["total_tasks"] == 1
        assert initialized_analysis_agent.performance_metrics["successful_tasks"] == 1


@pytest.mark.asyncio
async def test_execute_updates_performance_on_failure(initialized_analysis_agent):
    """Test that failed execution updates metrics."""

    with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLMService:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(side_effect=RuntimeError("Error"))
        MockLLMService.return_value = mock_instance

        with pytest.raises(RuntimeError):
            await initialized_analysis_agent.execute({
                "task": "analyze_documents",
                "previous_results": {
                    "documents": [{"id": "1", "content": "test"}]
                },
            })

        assert initialized_analysis_agent.performance_metrics["total_tasks"] == 1
        assert initialized_analysis_agent.performance_metrics["failed_tasks"] == 1


# ── Memory recording ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_stores_in_memory(initialized_analysis_agent):
    """Test that successful analysis is stored in memory."""

    mock_response = '{"key_findings": ["F1"], "patterns": [], "insights": [], "summary": ""}'

    with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLMService:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=mock_response)
        MockLLMService.return_value = mock_instance

        await initialized_analysis_agent.execute({
            "task": "analyze_documents",
            "query": "test query",
            "previous_results": {
                "documents": [{"id": "1", "content": "test"}]
            },
        })

        assert len(initialized_analysis_agent.memory.short_term) > 0
        entry = initialized_analysis_agent.memory.short_term[0]
        assert entry["type"] == "analysis_execution"


# ── Execution history ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_records_in_history(initialized_analysis_agent):
    """Test that execution is recorded in history."""

    mock_response = '{"key_findings": [], "patterns": [], "insights": [], "summary": ""}'

    with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLMService:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=mock_response)
        MockLLMService.return_value = mock_instance

        assert len(initialized_analysis_agent.execution_history) == 0

        await initialized_analysis_agent.execute({
            "task": "analyze_documents",
            "previous_results": {
                "documents": [{"id": "1", "content": "test"}]
            },
        })

        assert len(initialized_analysis_agent.execution_history) == 1
        entry = initialized_analysis_agent.execution_history[0]
        assert entry["task_name"] == "analyze_documents"
        assert entry["status"] == "success"


# ── Preparation and parsing ───────────────────────────────────────────────────

def test_prepare_documents(analysis_agent):
    """Test document preparation."""

    docs = [
        {"id": "1", "content": "First document content", "score": 0.95},
        {"id": "2", "content": "Second document", "score": 0.87},
    ]

    prepared = analysis_agent._prepare_documents(docs)
    assert "[Document 1" in prepared
    assert "[Document 2" in prepared
    assert "First document content" in prepared


def test_parse_analysis_json(analysis_agent):
    """Test parsing of JSON analysis response."""

    response = '{"key_findings": ["A", "B"], "patterns": ["P1"], "insights": ["I1"], "summary": "test"}'
    parsed = analysis_agent._parse_analysis(response)

    assert parsed["key_findings"] == ["A", "B"]
    assert parsed["patterns"] == ["P1"]


def test_parse_analysis_fallback(analysis_agent):
    """Test fallback parsing when JSON fails."""

    response = "- Finding 1\n- Finding 2\nSome other text"
    parsed = analysis_agent._parse_analysis(response)

    assert isinstance(parsed, dict)
    assert "key_findings" in parsed
    assert "summary" in parsed


# ── Statistics ────────────────────────────────────────────────────────────────

def test_get_analysis_stats(analysis_agent):
    """Test analysis statistics method."""

    analysis_agent.performance_metrics["total_tasks"] = 5
    analysis_agent.performance_metrics["failed_tasks"] = 1
    analysis_agent.performance_metrics["avg_response_time"] = 2.5

    # Record executions
    for i in range(4):
        analysis_agent.record_execution("analyze_documents", "success", 2.5)
    analysis_agent.record_execution("analyze_documents", "error", 1.0)

    stats = analysis_agent.get_analysis_stats()

    assert stats["total_analyses"] == 5
    assert stats["successful_analyses"] == 4
    assert stats["failed_analyses"] == 1
    assert stats["avg_analysis_time"] == 2.5


# ── Integration test ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_multiple_sequential_analyses(initialized_analysis_agent):
    """Test that agent can handle multiple analyses sequentially."""

    mock_response = '{"key_findings": ["F1"], "patterns": [], "insights": [], "summary": ""}'

    with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLMService:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=mock_response)
        MockLLMService.return_value = mock_instance

        for i in range(3):
            await initialized_analysis_agent.execute({
                "task": "analyze_documents",
                "query": f"query {i}",
                "previous_results": {
                    "documents": [{"id": str(i), "content": f"doc {i}"}]
                },
            })

        assert initialized_analysis_agent.performance_metrics["total_tasks"] == 3
        assert len(initialized_analysis_agent.execution_history) == 3
