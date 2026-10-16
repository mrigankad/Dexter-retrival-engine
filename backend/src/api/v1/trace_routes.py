from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, status

from src.core.dependency_injection import CurrentUser
from src.services.traces import get_trace, list_traces

router = APIRouter()


@router.get("")
async def traces(user: CurrentUser, limit: int = 50, session_id: Optional[str] = None):
    return {"traces": await list_traces(limit=limit, session_id=session_id)}


@router.get("/{trace_id}")
async def trace(trace_id: str, user: CurrentUser):
    data = await get_trace(trace_id)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trace not found")
    return data
