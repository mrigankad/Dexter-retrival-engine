"""
Agent Memory System

Two-tier memory:
  short_term  — last N interactions (in-memory, rolling window)
  long_term   — important facts that survive beyond the window
"""

from typing import Dict, Any, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

_IMPORTANCE_THRESHOLD = 0.7   # items above this go to long-term memory
_PROMOTE_THRESHOLD    = 0.6   # items above this get promoted when rolling


class AgentMemory:
    """Memory store for a single agent."""

    def __init__(self, agent_name: str, max_short_term: int = 20):
        self.agent_name = agent_name
        self.max_short_term = max_short_term
        self.short_term: List[Dict[str, Any]] = []
        self.long_term:  List[Dict[str, Any]] = []
        logger.debug(f"Memory initialised for agent: {agent_name}")

    # ── Write ──────────────────────────────────────────────────────────────────

    async def store(self, item: Dict[str, Any]) -> None:
        """
        Store an item in memory.

        High-importance items (importance > 0.7) also go into long-term memory.
        When short-term overflows the rolling window the oldest items are
        promoted to long-term if their importance exceeds 0.6.

        Args:
            item: arbitrary dict; 'importance' key (0-1) is optional.
        """
        item.setdefault("timestamp", datetime.now().isoformat())
        item.setdefault("agent", self.agent_name)

        importance = item.get("importance", 0.5)

        self.short_term.append(item)

        if importance > _IMPORTANCE_THRESHOLD:
            self.long_term.append(item)
            logger.debug(f"{self.agent_name}: item stored in long-term memory")

        # Roll the short-term window
        if len(self.short_term) > self.max_short_term:
            evicted = self.short_term[: -self.max_short_term]
            for old_item in evicted:
                if (
                    old_item.get("importance", 0.5) > _PROMOTE_THRESHOLD
                    and old_item not in self.long_term
                ):
                    self.long_term.append(old_item)
            self.short_term = self.short_term[-self.max_short_term :]

    # ── Read ───────────────────────────────────────────────────────────────────

    async def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Return the most recent memories that contain *query* as a substring.

        Args:
            query:  keyword to search for (case-insensitive)
            top_k:  max results to return
        """
        query_lower = query.lower()
        matched = [
            m for m in (self.short_term + self.long_term)
            if query_lower in str(m).lower()
        ]
        # Most-recent first
        matched.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return matched[:top_k]

    async def retrieve_by_type(self, memory_type: str) -> List[Dict[str, Any]]:
        """Return all memories of a given type."""
        return [
            m for m in (self.short_term + self.long_term)
            if m.get("type") == memory_type
        ]

    # ── Maintenance ────────────────────────────────────────────────────────────

    async def clear(self) -> None:
        """Wipe all memory (used in tests and GDPR deletion)."""
        self.short_term = []
        self.long_term  = []
        logger.info(f"Memory cleared for agent: {self.agent_name}")

    async def clear_short_term(self) -> None:
        """Clear only the short-term buffer."""
        self.short_term = []

    # ── Dunder helpers ─────────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self.short_term) + len(self.long_term)

    def __repr__(self) -> str:
        return (
            f"<AgentMemory(agent={self.agent_name}, "
            f"short_term={len(self.short_term)}, "
            f"long_term={len(self.long_term)})>"
        )
