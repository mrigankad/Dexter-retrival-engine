"""Unit tests for SynthesisAgent"""

import pytest
from unittest.mock import AsyncMock, patch
from src.agents.core.synthesis_agent import SynthesisAgent


@pytest.fixture
def synthesis_agent():
    agent = SynthesisAgent()
    return agent


@pytest.fixture
async def initialized_synthesis_agent(synthesis_agent):
    await synthesis_agent.initialize_memory()
    return synthesis_agent


# ── Agent properties ──────────────────────────────────────────────────────────

def test_synthesis_agent_has_correct_name_and_role(synthesis_agent):
    assert synthesis_agent.name == "SynthesisAgent"
    assert synthesis_agent.role == "Response Synthesis Specialist"


def test_synthesis_agent_inherits_from_agent(synthesis_agent):
    assert hasattr(synthesis_agent, "memory")
    assert hasattr(synthesis_agent, "execute")
    assert hasattr(synthesis_agent, "performance_metrics")


# ── Think method ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_think_returns_strategy_dict(synthesis_agent):
    strategy = await synthesis_agent.think(
        "test query",
        {"documents": [{"content": "doc1"}]},
        {"key_findings": ["f1"]},
        {"verification": {"confidence_score": 0.8}}
    )
    assert isinstance(strategy, dict)
    assert "integrate_all_sources" in strategy
    assert "confidence_threshold" in strategy


@pytest.mark.asyncio
async def test_think_adjusts_strategy_for_low_verification(synthesis_agent):
    strategy = await synthesis_agent.think(
        "query",
        {"documents": [{"content": "doc"}]},
        {"key_findings": ["f1"]},
        {"verification": {"confidence_score": 0.3}}
    )
    assert strategy["depth_level"] == "cautious"
    assert strategy["confidence_threshold"] == 0.5


@pytest.mark.asyncio
async def test_think_adjusts_strategy_without_analysis(synthesis_agent):
    strategy = await synthesis_agent.think(
        "query",
        {"documents": [{"content": "doc"}]},
        {},
        {}
    )
    assert strategy["depth_level"] == "shallow"


# ── Execute - success case ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_synthesizes_response(initialized_synthesis_agent):
    """Test that execute calls LLM service correctly."""

    mock_response = """{
        "response": "Comprehensive answer to the query",
        "limitations": ["Limited by source availability"],
        "summary": "Summary of the response"
    }"""

    with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLMService:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=mock_response)
        MockLLMService.return_value = mock_instance

        result = await initialized_synthesis_agent.execute({
            "task": "synthesize_response",
            "query": "What is AI?",
            "previous_results": {
                "search_results": {
                    "documents": [
                        {"id": "1", "content": "AI is...", "score": 0.95},
                        {"id": "2", "content": "Machine learning...", "score": 0.87},
                    ]
                },
                "analysis_results": {
                    "key_findings": ["Finding 1", "Finding 2"]
                },
                "verification_results": {
                    "verification": {
                        "verified": True,
                        "confidence_score": 0.9,
                        "issues": []
                    }
                },
            },
        })

        # Verify result structure
        assert result["status"] == "success"
        assert "response" in result
        assert "confidence_score" in result
        assert isinstance(result["confidence_score"], float)
        assert "sources" in result
        assert "reasoning_trace" in result
        assert "execution_time" in result


# ── Execute - failure cases ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_raises_on_wrong_task(initialized_synthesis_agent):
    """Test that SynthesisAgent only handles synthesize_response task."""

    with pytest.raises(ValueError, match="only handles 'synthesize_response'"):
        await initialized_synthesis_agent.execute({
            "task": "wrong_task",
            "query": "query",
            "previous_results": {
                "search_results": {"documents": [{"content": "test"}]}
            },
        })


@pytest.mark.asyncio
async def test_execute_requires_query(initialized_synthesis_agent):
    """Test that query is required."""

    with pytest.raises(ValueError, match="No query provided"):
        await initialized_synthesis_agent.execute({
            "task": "synthesize_response",
            "query": "",
            "previous_results": {
                "search_results": {"documents": [{"content": "test"}]}
            },
        })


@pytest.mark.asyncio
async def test_execute_requires_previous_results(initialized_synthesis_agent):
    """Test that previous results are required."""

    with pytest.raises(ValueError, match="No previous results provided"):
        await initialized_synthesis_agent.execute({
            "task": "synthesize_response",
            "query": "test query",
            "previous_results": {},
        })


@pytest.mark.asyncio
async def test_execute_requires_search_results(initialized_synthesis_agent):
    """Test that search results are required."""

    with pytest.raises(ValueError, match="No search results provided"):
        await initialized_synthesis_agent.execute({
            "task": "synthesize_response",
            "query": "test query",
            "previous_results": {
                "analysis_results": {"key_findings": ["f1"]},
            },
        })


@pytest.mark.asyncio
async def test_execute_propagates_llm_errors(initialized_synthesis_agent):
    """Test that errors from LLM service are propagated."""

    with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLMService:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(
            side_effect=RuntimeError("Synthesis failed")
        )
        MockLLMService.return_value = mock_instance

        with pytest.raises(RuntimeError, match="Synthesis failed"):
            await initialized_synthesis_agent.execute({
                "task": "synthesize_response",
                "query": "test",
                "previous_results": {
                    "search_results": {
                        "documents": [{"id": "1", "content": "test"}]
                    }
                },
            })


# ── Performance tracking ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_updates_performance_on_success(initialized_synthesis_agent):
    """Test that successful execution updates metrics."""

    mock_response = """{
        "response": "Answer",
        "limitations": [],
        "summary": "Summary"
    }"""

    with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLMService:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=mock_response)
        MockLLMService.return_value = mock_instance

        assert initialized_synthesis_agent.performance_metrics["total_tasks"] == 0

        await initialized_synthesis_agent.execute({
            "task": "synthesize_response",
            "query": "test",
            "previous_results": {
                "search_results": {
                    "documents": [{"id": "1", "content": "test"}]
                }
            },
        })

        assert initialized_synthesis_agent.performance_metrics["total_tasks"] == 1
        assert initialized_synthesis_agent.performance_metrics["successful_tasks"] == 1


@pytest.mark.asyncio
async def test_execute_updates_performance_on_failure(initialized_synthesis_agent):
    """Test that failed execution updates metrics."""

    with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLMService:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(side_effect=RuntimeError("Error"))
        MockLLMService.return_value = mock_instance

        with pytest.raises(RuntimeError):
            await initialized_synthesis_agent.execute({
                "task": "synthesize_response",
                "query": "test",
                "previous_results": {
                    "search_results": {
                        "documents": [{"id": "1", "content": "test"}]
                    }
                },
            })

        assert initialized_synthesis_agent.performance_metrics["total_tasks"] == 1
        assert initialized_synthesis_agent.performance_metrics["failed_tasks"] == 1


# ── Memory recording ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_stores_in_memory(initialized_synthesis_agent):
    """Test that synthesis is stored in memory."""

    mock_response = """{
        "response": "Answer",
        "limitations": [],
        "summary": "Summary"
    }"""

    with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLMService:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=mock_response)
        MockLLMService.return_value = mock_instance

        await initialized_synthesis_agent.execute({
            "task": "synthesize_response",
            "query": "test query",
            "previous_results": {
                "search_results": {
                    "documents": [{"id": "1", "content": "test"}]
                }
            },
        })

        assert len(initialized_synthesis_agent.memory.short_term) > 0


# ── Execution history ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_records_in_history(initialized_synthesis_agent):
    """Test that execution is recorded in history."""

    mock_response = """{
        "response": "Answer",
        "limitations": [],
        "summary": "Summary"
    }"""

    with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLMService:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=mock_response)
        MockLLMService.return_value = mock_instance

        assert len(initialized_synthesis_agent.execution_history) == 0

        await initialized_synthesis_agent.execute({
            "task": "synthesize_response",
            "query": "test",
            "previous_results": {
                "search_results": {
                    "documents": [{"id": "1", "content": "test"}]
                }
            },
        })

        assert len(initialized_synthesis_agent.execution_history) == 1
        entry = initialized_synthesis_agent.execution_history[0]
        assert entry["task_name"] == "synthesize_response"
        assert entry["status"] == "success"


# ── Source extraction ──────────────────────────────────────────────────────────

def test_extract_sources(synthesis_agent):
    """Test source extraction from search results."""

    search_results = {
        "documents": [
            {
                "id": "1",
                "title": "Document 1",
                "content": "Content",
                "score": 0.95,
                "url": "http://example.com/1"
            },
            {
                "id": "2",
                "title": "Document 2",
                "content": "More content",
                "score": 0.87,
                "url": "http://example.com/2"
            },
        ]
    }

    sources = synthesis_agent._extract_sources(search_results)

    assert len(sources) == 2
    assert sources[0]["title"] == "Document 1"
    assert sources[0]["relevance"] == 0.95
    assert sources[1]["id"] == "2"


def test_extract_sources_with_fallback_title(synthesis_agent):
    """Test source extraction with missing title."""

    search_results = {
        "documents": [
            {"id": "1", "content": "Content", "score": 0.95}
        ]
    }

    sources = synthesis_agent._extract_sources(search_results)

    assert len(sources) == 1
    assert sources[0]["title"] == "1"  # Falls back to ID


# ── Reasoning trace ────────────────────────────────────────────────────────────

def test_generate_reasoning_trace(synthesis_agent):
    """Test reasoning trace generation."""

    trace = synthesis_agent._generate_reasoning_trace(
        "What is AI?",
        {"documents": [{"content": "doc1"}, {"content": "doc2"}]},
        {"key_findings": ["f1", "f2"]},
        {"verification": {"verified": True, "confidence_score": 0.9}}
    )

    assert len(trace) >= 4
    assert any("found" in str(step).lower() for step in trace)
    assert any("extracted" in str(step).lower() for step in trace)
    assert any("verified" in str(step).lower() for step in trace)


# ── Parsing ────────────────────────────────────────────────────────────────────

def test_parse_synthesis_json(synthesis_agent):
    """Test parsing of JSON synthesis response."""

    response = """{
        "response": "Comprehensive answer",
        "limitations": ["limited sources"],
        "summary": "Brief summary"
    }"""

    parsed = synthesis_agent._parse_synthesis(response)

    assert parsed["response"] == "Comprehensive answer"
    assert "limited sources" in parsed["limitations"]


def test_parse_synthesis_fallback(synthesis_agent):
    """Test fallback parsing when JSON fails."""

    response = "This is a plain text response without JSON"
    parsed = synthesis_agent._parse_synthesis(response)

    assert isinstance(parsed, dict)
    assert "response" in parsed
    assert "limitations" in parsed


# ── Confidence calculation ────────────────────────────────────────────────────

def test_calculate_confidence_with_verification(synthesis_agent):
    """Test confidence calculation with verification results."""

    synthesis_data = {"limitations": []}
    verification_results = {
        "verification": {"confidence_score": 0.9}
    }

    confidence = synthesis_agent._calculate_confidence(
        verification_results,
        synthesis_data
    )

    assert 0.75 < confidence <= 1.0


def test_calculate_confidence_with_limitations(synthesis_agent):
    """Test confidence reduces with limitations."""

    synthesis_data = {"limitations": ["Source limitation"]}
    verification_results = {
        "verification": {"confidence_score": 0.8}
    }

    confidence = synthesis_agent._calculate_confidence(
        verification_results,
        synthesis_data
    )

    assert confidence < 0.8  # Reduced due to limitations


def test_calculate_confidence_without_verification(synthesis_agent):
    """Test confidence calculation without verification."""

    synthesis_data = {"limitations": []}
    verification_results = {}

    confidence = synthesis_agent._calculate_confidence(
        verification_results,
        synthesis_data
    )

    assert confidence == 0.7  # Base confidence


# ── Statistics ────────────────────────────────────────────────────────────────

def test_get_synthesis_stats(synthesis_agent):
    """Test synthesis statistics method."""

    synthesis_agent.record_execution("synthesize_response", "success", 1.5)
    synthesis_agent.record_execution("synthesize_response", "success", 2.0)
    synthesis_agent.record_execution("synthesize_response", "error", 0.5)
    synthesis_agent.update_performance(True, 0.9, 1.5)
    synthesis_agent.update_performance(True, 0.85, 2.0)
    synthesis_agent.update_performance(False, 0.0, 0.5)

    stats = synthesis_agent.get_synthesis_stats()

    assert stats["total_syntheses"] == 3
    assert stats["successful_syntheses"] == 2
    assert stats["failed_syntheses"] == 1


# ── Integration test ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_multiple_sequential_syntheses(initialized_synthesis_agent):
    """Test multiple synthesis executions."""

    mock_response = """{
        "response": "Answer",
        "limitations": [],
        "summary": "Summary"
    }"""

    with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLMService:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=mock_response)
        MockLLMService.return_value = mock_instance

        for i in range(3):
            await initialized_synthesis_agent.execute({
                "task": "synthesize_response",
                "query": f"query {i}",
                "previous_results": {
                    "search_results": {
                        "documents": [{"id": str(i), "content": f"doc {i}"}]
                    }
                },
            })

        assert initialized_synthesis_agent.performance_metrics["total_tasks"] == 3
        assert len(initialized_synthesis_agent.execution_history) == 3
