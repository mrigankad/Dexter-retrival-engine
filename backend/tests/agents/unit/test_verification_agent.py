"""Unit tests for VerificationAgent"""

import pytest
from unittest.mock import AsyncMock, patch
from src.agents.core.verification_agent import VerificationAgent


@pytest.fixture
def verification_agent():
    agent = VerificationAgent()
    return agent


@pytest.fixture
async def initialized_verification_agent(verification_agent):
    await verification_agent.initialize_memory()
    return verification_agent


# ── Agent properties ──────────────────────────────────────────────────────────

def test_verification_agent_has_correct_name_and_role(verification_agent):
    assert verification_agent.name == "VerificationAgent"
    assert verification_agent.role == "Fact Verification Specialist"


def test_verification_agent_inherits_from_agent(verification_agent):
    assert hasattr(verification_agent, "memory")
    assert hasattr(verification_agent, "execute")
    assert hasattr(verification_agent, "performance_metrics")


# ── Think method ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_think_returns_strategy_dict(verification_agent):
    strategy = await verification_agent.think(
        ["Finding 1"],
        [{"content": "test"}]
    )
    assert isinstance(strategy, dict)
    assert "check_factuality" in strategy
    assert "confidence_threshold" in strategy


@pytest.mark.asyncio
async def test_think_lowers_threshold_for_few_docs(verification_agent):
    few_docs = [{"content": "doc1"}]
    strategy = await verification_agent.think(["Finding"], few_docs)
    assert strategy["confidence_threshold"] == 0.5


# ── Execute - success case ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_verifies_findings(initialized_verification_agent):
    """Test that execute calls LLM service correctly."""

    mock_response = """{
        "verified": true,
        "confidence_score": 0.87,
        "evidence_strength": 0.9,
        "issues": [],
        "summary": "All findings verified"
    }"""

    with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLMService:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=mock_response)
        MockLLMService.return_value = mock_instance

        result = await initialized_verification_agent.execute({
            "task": "verify_findings",
            "previous_results": {
                "key_findings": ["Finding 1", "Finding 2"],
                "documents": [
                    {"id": "1", "content": "Source document 1", "score": 0.95},
                    {"id": "2", "content": "Source document 2", "score": 0.87},
                ],
            },
        })

        # Verify result structure
        assert result["status"] == "success"
        assert "verified" in result
        assert "confidence_score" in result
        assert isinstance(result["confidence_score"], float)
        assert "issues" in result


# ── Execute - failure cases ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_raises_on_wrong_task(initialized_verification_agent):
    """Test that VerificationAgent only handles verify_findings task."""

    with pytest.raises(ValueError, match="only handles 'verify_findings'"):
        await initialized_verification_agent.execute({
            "task": "wrong_task",
            "previous_results": {
                "key_findings": ["Finding"],
                "documents": [{"content": "test"}]
            },
        })


@pytest.mark.asyncio
async def test_execute_requires_findings(initialized_verification_agent):
    """Test that findings are required."""

    with pytest.raises(ValueError, match="No findings provided"):
        await initialized_verification_agent.execute({
            "task": "verify_findings",
            "previous_results": {
                "key_findings": [],
                "documents": [{"content": "test"}]
            },
        })


@pytest.mark.asyncio
async def test_execute_requires_documents(initialized_verification_agent):
    """Test that documents are required."""

    with pytest.raises(ValueError, match="No documents provided"):
        await initialized_verification_agent.execute({
            "task": "verify_findings",
            "previous_results": {
                "key_findings": ["Finding 1"],
                "documents": []
            },
        })


@pytest.mark.asyncio
async def test_execute_propagates_llm_errors(initialized_verification_agent):
    """Test that errors from LLM service are propagated."""

    with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLMService:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(
            side_effect=RuntimeError("Verification failed")
        )
        MockLLMService.return_value = mock_instance

        with pytest.raises(RuntimeError, match="Verification failed"):
            await initialized_verification_agent.execute({
                "task": "verify_findings",
                "previous_results": {
                    "key_findings": ["Finding"],
                    "documents": [{"id": "1", "content": "test"}]
                },
            })


# ── Performance tracking ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_updates_performance_on_success(initialized_verification_agent):
    """Test that successful execution updates metrics."""

    mock_response = """{
        "verified": true,
        "confidence_score": 0.9,
        "evidence_strength": 0.85,
        "issues": [],
        "summary": "Good"
    }"""

    with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLMService:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=mock_response)
        MockLLMService.return_value = mock_instance

        assert initialized_verification_agent.performance_metrics["total_tasks"] == 0

        await initialized_verification_agent.execute({
            "task": "verify_findings",
            "previous_results": {
                "key_findings": ["F1"],
                "documents": [{"id": "1", "content": "test"}]
            },
        })

        assert initialized_verification_agent.performance_metrics["total_tasks"] == 1
        assert initialized_verification_agent.performance_metrics["successful_tasks"] == 1


# ── Memory recording ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_stores_in_memory(initialized_verification_agent):
    """Test that verification is stored in memory."""

    mock_response = """{
        "verified": true,
        "confidence_score": 0.85,
        "evidence_strength": 0.9,
        "issues": [],
        "summary": "Test"
    }"""

    with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLMService:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=mock_response)
        MockLLMService.return_value = mock_instance

        await initialized_verification_agent.execute({
            "task": "verify_findings",
            "previous_results": {
                "key_findings": ["Finding 1"],
                "documents": [{"id": "1", "content": "test"}]
            },
        })

        assert len(initialized_verification_agent.memory.short_term) > 0


# ── Parsing ───────────────────────────────────────────────────────────────────

def test_parse_verification_json(verification_agent):
    """Test parsing of JSON verification response."""

    response = """{
        "verified": true,
        "confidence_score": 0.85,
        "evidence_strength": 0.9,
        "issues": ["minor issue"],
        "summary": "Mostly verified"
    }"""

    parsed = verification_agent._parse_verification(response)
    assert parsed["verified"] is True
    assert parsed["confidence_score"] == 0.85


def test_parse_verification_fallback(verification_agent):
    """Test fallback parsing when JSON fails."""

    response = "This was not verified and has some issues"
    parsed = verification_agent._parse_verification(response)

    assert isinstance(parsed, dict)
    assert "verified" in parsed
    assert "confidence_score" in parsed


# ── Statistics ────────────────────────────────────────────────────────────────

def test_get_verification_stats(verification_agent):
    """Test verification statistics method."""

    verification_agent.record_execution("verify_findings", "success", 1.5)
    verification_agent.record_execution("verify_findings", "success", 2.0)
    verification_agent.record_execution("verify_findings", "error", 0.5)
    verification_agent.update_performance(True, 0.9, 1.5)
    verification_agent.update_performance(True, 0.85, 2.0)
    verification_agent.update_performance(False, 0.0, 0.5)

    stats = verification_agent.get_verification_stats()

    assert stats["total_verifications"] == 3
    assert stats["successful_verifications"] == 2
    assert stats["failed_verifications"] == 1


# ── Integration test ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_multiple_sequential_verifications(initialized_verification_agent):
    """Test multiple verification executions."""

    mock_response = """{
        "verified": true,
        "confidence_score": 0.8,
        "evidence_strength": 0.85,
        "issues": [],
        "summary": "OK"
    }"""

    with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLMService:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=mock_response)
        MockLLMService.return_value = mock_instance

        for i in range(3):
            await initialized_verification_agent.execute({
                "task": "verify_findings",
                "previous_results": {
                    "key_findings": [f"F{i}"],
                    "documents": [{"id": str(i), "content": f"doc {i}"}]
                },
            })

        assert initialized_verification_agent.performance_metrics["total_tasks"] == 3
        assert len(initialized_verification_agent.execution_history) == 3
