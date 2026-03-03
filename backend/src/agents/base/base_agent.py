"""
Base Agent Class

All agents (SearchAgent, AnalysisAgent, etc.) inherit from this class.
Provides: task execution, memory management, performance tracking, error handling.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)


class Agent(ABC):
    """
    Abstract base class for all agents.

    Every agent must:
    1. Have a name and role
    2. Implement execute() method
    3. Maintain memory of interactions
    4. Track performance metrics
    """

    def __init__(self, name: str, role: str):
        self.id = str(uuid.uuid4())
        self.name = name
        self.role = role

        self.tools: Dict[str, Any] = {}
        self.memory: Optional[Any] = None  # Set via initialize_memory()

        self.performance_metrics = {
            "total_tasks": 0,
            "successful_tasks": 0,
            "failed_tasks": 0,
            "total_response_time": 0.0,
            "avg_response_time": 0.0,
            "avg_quality_score": 0.0,
            "success_rate": 0.0,
            "last_updated": None,
        }

        self.execution_history: List[Dict[str, Any]] = []

        logger.info(f"Initialized agent: {self.name} ({self.role})")

    async def initialize_memory(self) -> None:
        """Initialize memory. Call this after creation."""
        from src.agents.base.agent_memory import AgentMemory
        self.memory = AgentMemory(self.name)

    @abstractmethod
    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a task. Must be implemented by subclasses.

        Args:
            task: {
                "task": "retrieve_documents",
                "query": "...",
                "previous_results": {...}   # from prior agent in chain
            }

        Returns:
            {"status": "success", ...task-specific keys...}
        """
        pass

    async def think(self, context: str) -> str:
        """Optional reasoning step before execution. Override in subclasses."""
        return ""

    async def observe(self, observation: Dict[str, Any]) -> None:
        """Store an observation in memory for future learning."""
        if self.memory is not None:
            observation.setdefault("timestamp", datetime.now().isoformat())
            observation.setdefault("agent", self.name)
            await self.memory.store(observation)

    async def learn_from_feedback(self, feedback: Dict[str, Any]) -> None:
        """Store user feedback for improvement."""
        await self.observe({
            "type": "user_feedback",
            "feedback": feedback,
            "importance": feedback.get("importance", 0.5),
        })

    def update_performance(
        self, success: bool, quality_score: float, response_time: float
    ) -> None:
        """Update performance metrics after each task."""
        m = self.performance_metrics
        m["total_tasks"] += 1
        m["total_response_time"] += response_time

        if success:
            m["successful_tasks"] += 1
        else:
            m["failed_tasks"] += 1

        total = m["total_tasks"]
        m["avg_response_time"] = m["total_response_time"] / total
        m["avg_quality_score"] = (
            (m["avg_quality_score"] * (total - 1) + quality_score) / total
        )
        m["success_rate"] = m["successful_tasks"] / total
        m["last_updated"] = datetime.now().isoformat()

        logger.debug(
            f"{self.name}: tasks={total}, "
            f"success_rate={m['success_rate']:.1%}, "
            f"avg_quality={m['avg_quality_score']:.2f}"
        )

    def record_execution(
        self,
        task_name: str,
        status: str,
        duration: float,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Record execution in history."""
        self.execution_history.append({
            "task_name": task_name,
            "status": status,
            "duration": duration,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        })

    def get_metrics(self) -> Dict[str, Any]:
        return self.performance_metrics.copy()

    def get_execution_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.execution_history[-limit:]

    async def reset(self) -> None:
        """Reset agent state (useful for tests)."""
        self.execution_history = []
        if self.memory:
            await self.memory.clear()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name}, role={self.role})>"


# ── Concrete test agent ────────────────────────────────────────────────────────

class EchoAgent(Agent):
    """Minimal concrete agent used only for testing the base class."""

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "success",
            "result": f"Executed task: {task.get('task', 'unknown')}",
            "agent": self.name,
        }


# Keep backward-compatible alias (tests import TestAgent)
TestAgent = EchoAgent
