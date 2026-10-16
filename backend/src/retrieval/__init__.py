"""Retrieval core: fusion, hybrid retriever over Qdrant, context assembly."""

from .fusion import reciprocal_rank_fusion, dedupe_chunks
from .hybrid_retriever import HybridRetriever, get_hybrid_retriever
from .context_builder import ContextBuilder, BuiltContext

__all__ = [
    "reciprocal_rank_fusion", "dedupe_chunks",
    "HybridRetriever", "get_hybrid_retriever",
    "ContextBuilder", "BuiltContext",
]
