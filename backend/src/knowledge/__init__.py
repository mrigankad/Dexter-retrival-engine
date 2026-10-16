"""
Knowledge adapters: one interface, many backends.

    local      – this engine's Qdrant hybrid index (default)
    foundry_iq – Microsoft Foundry IQ / Azure AI Search agentic retrieval
    mock       – in-memory keyword scorer for tests and offline demos

The orchestrator only ever calls ``adapter.retrieve(RetrievalRequest)``.
"""

from .base import KnowledgeAdapter, AdapterCapabilities
from .local_adapter import LocalKnowledgeAdapter
from .foundry_iq_adapter import FoundryIQAdapter, FoundryIQError
from .mock_adapter import MockKnowledgeAdapter
from .registry import get_knowledge_adapter, list_backends, register_adapter, reset_registry

__all__ = [
    "KnowledgeAdapter", "AdapterCapabilities",
    "LocalKnowledgeAdapter", "FoundryIQAdapter", "FoundryIQError", "MockKnowledgeAdapter",
    "get_knowledge_adapter", "list_backends", "register_adapter", "reset_registry",
]
