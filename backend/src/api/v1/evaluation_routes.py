"""Evaluation endpoints: per-message scores (UI) and the offline eval harness."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from src.core.dependency_injection import ChatUser, CurrentUser, DbSession
from src.infrastructure.database import Evaluation

router = APIRouter()


class EvalRunRequest(BaseModel):
    dataset_path: str = Field(default="evals/datasets/sample.json")
    top_k: int = Field(default=8, ge=1, le=50)
    judge: bool = Field(default=False, description="Also run LLM-judged faithfulness/relevance")
    backend: Optional[str] = None
    max_questions: Optional[int] = Field(default=None, ge=1)


@router.get("/{message_id}")
async def message_evaluation(message_id: str, db: DbSession, user: ChatUser):
    try:
        mid = uuid.UUID(message_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No evaluation")
    row = await db.scalar(select(Evaluation).where(Evaluation.message_id == mid))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No evaluation for this message")
    return {"message_id": message_id, "faithfulness": row.faithfulness, "relevance": row.relevance,
            "precision": row.precision, "recall": row.recall, "overall_score": row.overall_score, "details": row.details}


@router.post("/run")
async def run_evaluation(body: EvalRunRequest, user: CurrentUser) -> Dict[str, Any]:
    from src.evaluation import EvalHarness, load_dataset
    try:
        dataset = load_dataset(body.dataset_path)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Dataset not found: {body.dataset_path}")
    if body.max_questions:
        dataset = dataset[: body.max_questions]
    harness = EvalHarness(backend=body.backend)
    report = await harness.run(dataset, top_k=body.top_k, judge=body.judge)
    return report.model_dump()
