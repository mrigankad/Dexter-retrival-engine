"""
Agent Communication Bus

Central hub for inter-agent messaging.
Supports direct messages, pub/sub broadcasts, and message history.
"""

import asyncio
import uuid
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentMessage:
    """Immutable message envelope passed between agents."""

    sender:       str
    recipient:    str          # "" = broadcast
    message_type: str          # "request" | "response" | "update" | "query"
    content:      Dict[str, Any]
    priority:     int   = 1    # 1 = low … 5 = high
    message_id:   str   = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp:    float = field(default_factory=lambda: datetime.now().timestamp())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id":   self.message_id,
            "sender":       self.sender,
            "recipient":    self.recipient,
            "message_type": self.message_type,
            "content":      self.content,
            "priority":     self.priority,
            "timestamp":    self.timestamp,
        }


class AgentCommunicationBus:
    """
    Central messaging hub for the agent system.

    Features
    --------
    * Direct messages  – send to one specific agent
    * Broadcasts       – fanout to all subscribers of a message_type
    * History          – full audit trail, filterable by agent
    * Handlers         – register callables that fire on message types
    """

    def __init__(self) -> None:
        self._queue:         asyncio.Queue          = asyncio.Queue()
        self.subscriptions:  Dict[str, List[str]]   = defaultdict(list)
        self.message_history: List[Dict[str, Any]]  = []
        self.handlers:       Dict[str, List[Callable]] = defaultdict(list)
        logger.info("AgentCommunicationBus initialised")

    # ── Send / Broadcast ───────────────────────────────────────────────────────

    async def send_message(self, message: AgentMessage) -> str:
        """
        Enqueue a message and append it to the history log.

        Returns the message_id for caller reference.
        """
        self.message_history.append(message.to_dict())
        await self._queue.put(message)
        logger.debug(
            f"Message enqueued: {message.sender} → {message.recipient} "
            f"[{message.message_type}]"
        )

        # Fire any registered handlers
        for handler in self.handlers.get(message.message_type, []):
            try:
                await handler(message)
            except Exception as exc:
                logger.warning(f"Handler error for {message.message_type}: {exc}")

        return message.message_id

    async def broadcast(self, message: AgentMessage) -> None:
        """Send *message* to every agent subscribed to its message_type."""
        targets = self.subscriptions.get(message.message_type, [])
        for agent_name in targets:
            if agent_name == message.sender:
                continue  # Don't echo back to sender
            await self.send_message(
                AgentMessage(
                    sender=message.sender,
                    recipient=agent_name,
                    message_type=message.message_type,
                    content=message.content,
                    priority=message.priority,
                )
            )

    # ── Subscription ──────────────────────────────────────────────────────────

    async def subscribe(self, agent_name: str, message_types: List[str]) -> None:
        """Subscribe *agent_name* to one or more message types."""
        for msg_type in message_types:
            if agent_name not in self.subscriptions[msg_type]:
                self.subscriptions[msg_type].append(agent_name)
        logger.debug(f"{agent_name} subscribed to: {message_types}")

    async def unsubscribe(self, agent_name: str, message_types: List[str]) -> None:
        """Remove *agent_name* from subscriptions."""
        for msg_type in message_types:
            subs = self.subscriptions.get(msg_type, [])
            if agent_name in subs:
                subs.remove(agent_name)

    async def register_handler(
        self, message_type: str, handler: Callable
    ) -> None:
        """Register an async callable that fires whenever *message_type* is sent."""
        self.handlers[message_type].append(handler)

    # ── Consume ───────────────────────────────────────────────────────────────

    async def get_next_message(
        self, agent_name: Optional[str] = None
    ) -> Optional[AgentMessage]:
        """
        Non-blocking peek at the next message.

        If *agent_name* is provided, only messages addressed to that agent
        are returned; others are re-queued.
        """
        try:
            message = self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

        if agent_name and message.recipient not in (agent_name, ""):
            await self._queue.put(message)  # Not for this agent – put back
            return None

        return message

    # ── Inspection ────────────────────────────────────────────────────────────

    def get_history(
        self, agent_name: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Return message history, optionally filtered by sender or recipient."""
        history = self.message_history
        if agent_name:
            history = [
                m for m in history
                if m["sender"] == agent_name or m["recipient"] == agent_name
            ]
        return history[-limit:]

    def get_statistics(self) -> Dict[str, Any]:
        return {
            "total_messages":      len(self.message_history),
            "active_subscriptions": sum(len(v) for v in self.subscriptions.values()),
            "queue_size":           self._queue.qsize(),
        }

    async def clear_history(self) -> None:
        self.message_history = []

    def __repr__(self) -> str:
        return (
            f"<AgentCommunicationBus("
            f"messages={len(self.message_history)}, "
            f"queue={self._queue.qsize()})>"
        )
