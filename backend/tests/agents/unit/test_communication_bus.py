"""Unit tests for communication_bus.py"""

import pytest
from src.agents.communication.communication_bus import AgentCommunicationBus, AgentMessage


@pytest.fixture
def bus():
    return AgentCommunicationBus()


def make_msg(sender="A", recipient="B", msg_type="request", content=None):
    return AgentMessage(
        sender=sender,
        recipient=recipient,
        message_type=msg_type,
        content=content or {"data": "test"},
    )


# ── Init ──────────────────────────────────────────────────────────────────────

def test_bus_starts_empty(bus):
    assert bus.message_history == []
    assert bus._queue.qsize() == 0


def test_repr(bus):
    assert "AgentCommunicationBus" in repr(bus)


# ── Message creation ──────────────────────────────────────────────────────────

def test_message_has_auto_id():
    msg = make_msg()
    assert msg.message_id is not None
    assert len(msg.message_id) > 0


def test_two_messages_have_different_ids():
    assert make_msg().message_id != make_msg().message_id


def test_message_to_dict():
    msg = make_msg()
    d = msg.to_dict()
    assert d["sender"]    == "A"
    assert d["recipient"] == "B"
    assert "message_id" in d
    assert "timestamp"  in d


# ── Send ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_returns_message_id(bus):
    msg_id = await bus.send_message(make_msg())
    assert isinstance(msg_id, str)


@pytest.mark.asyncio
async def test_send_adds_to_history(bus):
    await bus.send_message(make_msg())
    assert len(bus.message_history) == 1


@pytest.mark.asyncio
async def test_send_adds_to_queue(bus):
    await bus.send_message(make_msg())
    assert bus._queue.qsize() == 1


# ── Consume ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_next_message_returns_message(bus):
    await bus.send_message(make_msg(recipient="Bob"))
    msg = await bus.get_next_message("Bob")
    assert msg is not None
    assert msg.recipient == "Bob"


@pytest.mark.asyncio
async def test_get_next_message_returns_none_when_empty(bus):
    msg = await bus.get_next_message("Bob")
    assert msg is None


@pytest.mark.asyncio
async def test_get_next_message_requeues_wrong_recipient(bus):
    await bus.send_message(make_msg(recipient="Alice"))
    msg = await bus.get_next_message("Bob")
    assert msg is None
    # Message should still be in queue
    assert bus._queue.qsize() == 1


# ── Subscribe / Broadcast ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_subscribe_adds_agent(bus):
    await bus.subscribe("Agent1", ["update"])
    assert "Agent1" in bus.subscriptions["update"]


@pytest.mark.asyncio
async def test_subscribe_idempotent(bus):
    await bus.subscribe("Agent1", ["update"])
    await bus.subscribe("Agent1", ["update"])
    assert bus.subscriptions["update"].count("Agent1") == 1


@pytest.mark.asyncio
async def test_unsubscribe_removes_agent(bus):
    await bus.subscribe("Agent1", ["update"])
    await bus.unsubscribe("Agent1", ["update"])
    assert "Agent1" not in bus.subscriptions.get("update", [])


@pytest.mark.asyncio
async def test_broadcast_sends_to_all_subscribers(bus):
    await bus.subscribe("Agent1", ["news"])
    await bus.subscribe("Agent2", ["news"])

    await bus.broadcast(make_msg(sender="Source", msg_type="news"))
    stats = bus.get_statistics()
    # 2 messages should have been sent (one per subscriber)
    assert stats["total_messages"] == 2


@pytest.mark.asyncio
async def test_broadcast_does_not_echo_to_sender(bus):
    await bus.subscribe("Source", ["news"])

    await bus.broadcast(make_msg(sender="Source", msg_type="news"))
    # No message should be echoed back to Source
    assert all(
        m["recipient"] != "Source" for m in bus.message_history
    )


# ── History ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_history_all(bus):
    await bus.send_message(make_msg("A", "B"))
    await bus.send_message(make_msg("C", "D"))
    assert len(bus.get_history()) == 2


@pytest.mark.asyncio
async def test_get_history_filtered_by_agent(bus):
    await bus.send_message(make_msg("Alice", "Bob"))
    await bus.send_message(make_msg("Carol", "Dave"))
    assert len(bus.get_history("Alice")) == 1


@pytest.mark.asyncio
async def test_get_history_limit(bus):
    for _ in range(10):
        await bus.send_message(make_msg())
    assert len(bus.get_history(limit=3)) == 3


@pytest.mark.asyncio
async def test_clear_history(bus):
    await bus.send_message(make_msg())
    await bus.clear_history()
    assert bus.message_history == []


# ── Statistics ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_statistics(bus):
    await bus.send_message(make_msg())
    stats = bus.get_statistics()
    assert stats["total_messages"] == 1
    assert "queue_size" in stats


# ── Handler ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handler_called_on_send(bus):
    received = []

    async def my_handler(msg: AgentMessage):
        received.append(msg)

    await bus.register_handler("request", my_handler)
    await bus.send_message(make_msg(msg_type="request"))
    assert len(received) == 1
