"""Adapter registry: resolve a backend name (or the configured default) to an instance."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from src.core.config import settings
from src.core.logger import get_logger

from .base import KnowledgeAdapter
from .foundry_iq_adapter import FoundryIQAdapter
from .local_adapter import LocalKnowledgeAdapter
from .mcp_adapter import McpKnowledgeAdapter
from .mock_adapter import MockKnowledgeAdapter

logger = get_logger(__name__)

_factories: Dict[str, Callable[[], KnowledgeAdapter]] = {
    "local": LocalKnowledgeAdapter,
    "foundry_iq": FoundryIQAdapter,
    "mcp": McpKnowledgeAdapter,
    "mock": MockKnowledgeAdapter,
}
_instances: Dict[str, KnowledgeAdapter] = {}


def register_adapter(name: str, factory: Callable[[], KnowledgeAdapter], instance: Optional[KnowledgeAdapter] = None) -> None:
    _factories[name] = factory
    if instance is not None:
        _instances[name] = instance
    else:
        _instances.pop(name, None)


def get_knowledge_adapter(name: Optional[str] = None) -> KnowledgeAdapter:
    name = name or settings.knowledge_backend
    if name not in _factories:
        raise KeyError(f"Unknown knowledge backend '{name}'. Available: {sorted(_factories)}")
    if name not in _instances:
        _instances[name] = _factories[name]()
        logger.info("Knowledge adapter initialised", backend=name)
    return _instances[name]


def list_backends() -> List[Dict[str, object]]:
    out = []
    for name in sorted(_factories):
        try:
            adapter = get_knowledge_adapter(name)
            info = adapter.describe()
        except Exception as exc:  # pragma: no cover
            info = {"backend": name, "error": str(exc)}
        info["default"] = name == settings.knowledge_backend
        info["fallback"] = name == settings.knowledge_fallback_backend
        out.append(info)
    return out


def reset_registry() -> None:
    _instances.clear()
