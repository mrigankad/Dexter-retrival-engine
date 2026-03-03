"""Unit tests for base_agent.py"""

import pytest
from src.agents.base.base_agent import Agent, TestAgent


@pytest.fixture
def agent():
    return TestAgent(name="TestAgent", role="Tester")


# ── Creation ──────────────────────────────────────────────────────────────────

def test_agent_has_name_and_role(agent):
    assert agent.name == "TestAgent"
    assert agent.role == "Tester"


def test_agent_has_unique_id(agent):
    other = TestAgent(name="Other", role="Other")
    assert agent.id != other.id


def test_agent_repr(agent):
    assert "TestAgent" in repr(agent)


# ── Execute ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_returns_dict(agent):
    result = await agent.execute({"task": "do_something"})
    assert isinstance(result, dict)
    assert result["status"] == "success"


# ── Memory ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_memory_is_none_before_init(agent):
    assert agent.memory is None


@pytest.mark.asyncio
async def test_memory_available_after_init(agent):
    await agent.initialize_memory()
    assert agent.memory is not None


# ── Performance tracking ──────────────────────────────────────────────────────

def test_initial_metrics_are_zero(agent):
    m = agent.performance_metrics
    assert m["total_tasks"]      == 0
    assert m["successful_tasks"] == 0
    assert m["failed_tasks"]     == 0


def test_update_performance_success(agent):
    agent.update_performance(success=True, quality_score=0.9, response_time=1.0)
    m = agent.performance_metrics
    assert m["total_tasks"]      == 1
    assert m["successful_tasks"] == 1
    assert m["failed_tasks"]     == 0
    assert m["success_rate"]     == 1.0
    assert m["avg_quality_score"] == pytest.approx(0.9)
    assert m["avg_response_time"] == pytest.approx(1.0)


def test_update_performance_failure(agent):
    agent.update_performance(success=False, quality_score=0.1, response_time=2.0)
    m = agent.performance_metrics
    assert m["failed_tasks"]  == 1
    assert m["success_rate"]  == 0.0


def test_success_rate_across_multiple_tasks(agent):
    agent.update_performance(True,  0.9, 1.0)
    agent.update_performance(True,  0.8, 1.0)
    agent.update_performance(False, 0.2, 1.0)
    assert agent.performance_metrics["success_rate"] == pytest.approx(2 / 3)


# ── Execution history ─────────────────────────────────────────────────────────

def test_record_execution_stores_entry(agent):
    agent.record_execution("my_task", "success", 1.5, {"key": "val"})
    history = agent.get_execution_history()
    assert len(history) == 1
    entry = history[0]
    assert entry["task_name"] == "my_task"
    assert entry["status"]    == "success"
    assert entry["duration"]  == 1.5
    assert entry["metadata"]["key"] == "val"


def test_get_execution_history_respects_limit(agent):
    for i in range(15):
        agent.record_execution(f"task_{i}", "success", 0.1)
    assert len(agent.get_execution_history(limit=5)) == 5


# ── Reset ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reset_clears_history(agent):
    await agent.initialize_memory()
    agent.record_execution("task", "success", 1.0)
    await agent.reset()
    assert agent.execution_history == []


# ── Observe / feedback ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_observe_requires_memory(agent):
    # Without initializing memory, observe should not raise
    await agent.observe({"type": "test"})  # memory is None → no-op


@pytest.mark.asyncio
async def test_observe_stores_in_memory(agent):
    await agent.initialize_memory()
    await agent.observe({"type": "test", "content": "hello"})
    # Memory stores the item; verify short_term has at least one entry
    assert len(agent.memory.short_term) >= 1
