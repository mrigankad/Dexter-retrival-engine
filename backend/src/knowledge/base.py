from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from pydantic import BaseModel

from src.contracts import RetrievalRequest, RetrievalResult


class AdapterCapabilities(BaseModel):
    hybrid_search: bool = False
    reranking: bool = False
    query_planning: bool = False       # backend decomposes the question itself
    multimodal: bool = False
    permission_filters: bool = False
    returns_context: bool = False      # backend returns pre-assembled extractive context
    ingestion: bool = False            # we can push documents into it


class KnowledgeAdapter(ABC):
    """A knowledge backend that answers ``knowledge.retrieve`` tool calls."""

    name: str = "base"

    @abstractmethod
    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult: ...

    async def healthcheck(self) -> Dict[str, Any]:
        return {"backend": self.name, "status": "unknown"}

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities()

    def describe(self) -> Dict[str, Any]:
        return {"backend": self.name, "capabilities": self.capabilities().model_dump()}
