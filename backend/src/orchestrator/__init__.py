"""
Orchestrator: route → plan → execute tools → assemble evidence → synthesize once → trace.

Kept deliberately as *one* orchestrator with tools rather than a swarm of agents.
The legacy multi-agent package under ``src/agents`` remains available for
experimentation via ``/api/agents``.
"""

from .router import QueryRouter, RouteDecision
from .planner import QueryPlanner
from .executor import PlanExecutor, ExecutionResult
from .synthesizer import Synthesizer, resolve_citations
from .engine import RetrievalEngine, get_engine

__all__ = [
    "QueryRouter", "RouteDecision", "QueryPlanner", "PlanExecutor", "ExecutionResult",
    "Synthesizer", "resolve_citations", "RetrievalEngine", "get_engine",
]
