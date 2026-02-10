"""
Evaluation routes for retrieving quality scores.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any
import uuid

from db.postgres_models import Evaluation
from db.session_manager import async_session_factory
from sqlalchemy import select
from core.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

@router.get("/{message_id}")
async def get_evaluation(message_id: str):
    """
    Get evaluation scores for a specific chat message.
    """
    try:
        msg_uuid = uuid.UUID(message_id)
        async with async_session_factory() as session:
            stmt = select(Evaluation).where(Evaluation.message_id == msg_uuid)
            result = await session.execute(stmt)
            evaluation = result.scalar_one_or_none()
            
            if not evaluation:
                return {"status": "pending", "message": "Evaluation not found or still processing."}
                
            return {
                "status": "completed",
                "message_id": str(evaluation.message_id),
                "scores": {
                    "faithfulness": evaluation.faithfulness,
                    "relevance": evaluation.relevance,
                    "precision": evaluation.precision,
                    "recall": evaluation.recall
                }
            }
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid message_id format")
    except Exception as e:
        logger.error("Error fetching evaluation", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
