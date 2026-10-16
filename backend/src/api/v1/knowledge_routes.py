"""
Knowledge backends and the raw retrieve tool.

POST /knowledge/retrieve is the same contract an MCP ``knowledge_retrieve`` tool
exposes: query + filters → evidence, no synthesis.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.contracts import RetrievalFilters, RetrievalRequest
from src.core.config import settings
from src.core.dependency_injection import ChatUser
from src.knowledge import get_knowledge_adapter, list_backends

router = APIRouter()


class RetrieveIn(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)
    top_k: int = Field(default=8, ge=1, le=50)
    document_ids: Optional[List[str]] = None
    rerank: bool = True
    reasoning_effort: str = Field(default="low", pattern="^(minimal|low|medium)$")
    alternate_queries: List[str] = Field(default_factory=list)
    backend: Optional[str] = None


@router.get("/backends")
async def backends():
    return {"default": settings.knowledge_backend, "fallback": settings.knowledge_fallback_backend, "backends": list_backends()}


@router.get("/backends/{name}/health")
async def backend_health(name: str):
    try:
        adapter = get_knowledge_adapter(name)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return await adapter.healthcheck()


@router.post("/retrieve")
async def retrieve(body: RetrieveIn, user: ChatUser):
    try:
        adapter = get_knowledge_adapter(body.backend)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    request = RetrievalRequest(
        query=body.query, top_k=body.top_k, rerank=body.rerank, reasoning_effort=body.reasoning_effort,  # type: ignore[arg-type]
        alternate_queries=body.alternate_queries, filters=RetrievalFilters(document_ids=body.document_ids or None),
    )
    try:
        result = await adapter.retrieve(request)
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{adapter.name}: {exc}")
    return result.model_dump()
