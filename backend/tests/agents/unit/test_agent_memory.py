"""Unit tests for agent_memory.py"""

import pytest
from src.agents.base.agent_memory import AgentMemory


@pytest.fixture
def mem():
    return AgentMemory("TestAgent", max_short_term=5)


# ── Init ──────────────────────────────────────────────────────────────────────

def test_empty_on_creation(mem):
    assert len(mem) == 0
    assert mem.short_term == []
    assert mem.long_term  == []


def test_repr(mem):
    assert "TestAgent" in repr(mem)


# ── Store ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_store_adds_to_short_term(mem):
    await mem.store({"content": "hello"})
    assert len(mem.short_term) == 1


@pytest.mark.asyncio
async def test_store_adds_timestamp(mem):
    await mem.store({"content": "hi"})
    assert "timestamp" in mem.short_term[0]


@pytest.mark.asyncio
async def test_high_importance_goes_to_long_term(mem):
    await mem.store({"content": "critical fact", "importance": 0.9})
    assert len(mem.long_term) == 1


@pytest.mark.asyncio
async def test_low_importance_stays_short_term_only(mem):
    await mem.store({"content": "trivia", "importance": 0.3})
    assert len(mem.long_term) == 0


@pytest.mark.asyncio
async def test_rolling_window_evicts_old_items(mem):
    # max_short_term is 5
    for i in range(7):
        await mem.store({"content": f"item_{i}", "importance": 0.1})
    assert len(mem.short_term) == 5  # older items evicted


@pytest.mark.asyncio
async def test_rolling_window_promotes_important_items(mem):
    # Fill to trigger eviction; first item is important
    await mem.store({"content": "important", "importance": 0.8})
    for i in range(6):
        await mem.store({"content": f"filler_{i}", "importance": 0.1})
    # "important" was evicted from short_term but should be in long_term
    assert any("important" in str(m) for m in mem.long_term)


# ── Retrieve ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retrieve_by_keyword(mem):
    await mem.store({"content": "Python is great"})
    await mem.store({"content": "Java is verbose"})
    results = await mem.retrieve("Python")
    assert len(results) == 1
    assert "Python" in results[0]["content"]


@pytest.mark.asyncio
async def test_retrieve_returns_empty_when_no_match(mem):
    await mem.store({"content": "something"})
    results = await mem.retrieve("ZZZZ_no_match")
    assert results == []


@pytest.mark.asyncio
async def test_retrieve_respects_top_k(mem):
    for i in range(10):
        await mem.store({"content": f"match_{i}"})
    results = await mem.retrieve("match", top_k=3)
    assert len(results) <= 3


@pytest.mark.asyncio
async def test_retrieve_by_type(mem):
    await mem.store({"type": "fact",     "content": "a"})
    await mem.store({"type": "feedback", "content": "b"})
    facts = await mem.retrieve_by_type("fact")
    assert len(facts) == 1
    assert facts[0]["type"] == "fact"


# ── Clear ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_clear_wipes_everything(mem):
    await mem.store({"content": "x", "importance": 0.9})
    await mem.clear()
    assert len(mem) == 0


@pytest.mark.asyncio
async def test_clear_short_term_keeps_long_term(mem):
    await mem.store({"content": "important", "importance": 0.9})
    await mem.clear_short_term()
    assert len(mem.short_term) == 0
    assert len(mem.long_term)  == 1
