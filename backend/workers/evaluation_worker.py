"""
Evaluation Worker - Asynchronous quality scoring of RAG responses.
"""

import asyncio
import uuid
from typing import Dict, Any, List
from datetime import datetime

from core.logger import get_logger
from services.evaluation_service import EvaluationService
from db.postgres_models import ChatMessage, ChatSession, Evaluation
from db.session_manager import async_session_factory
from sqlalchemy import update, insert, select

logger = get_logger(__name__)

async def evaluate_and_store(
    query: str,
    response: str,
    contexts: List[str],
    message_id: str,
    session_id: str
):
    """
    Background task to evaluate a response and store the score.
    """
    service = EvaluationService()
    
    logger.info("Background evaluation started", message_id=message_id)
    
    # 1. Evaluate
    results = await service.evaluate_response(
        query=query,
        response=response,
        contexts=contexts
    )
    
    if results.get("status") == "error":
        logger.error("Background evaluation failed", message_id=message_id, error=results.get("error"))
        return

    # 2. Store scores in the Evaluations table
    try:
        async with async_session_factory() as session:
            # We assume session_id is a valid UUID string
            eval_id = uuid.uuid4()
            scores = results["scores"]
            
            stmt = insert(Evaluation).values(
                id=eval_id,
                message_id=uuid.UUID(message_id),
                session_id=uuid.UUID(session_id.replace("session_", "").split(".")[0]) if "session_" in session_id else uuid.uuid4(), # Fallback for POC session naming
                faithfulness=scores.get("faithfulness"),
                relevance=scores.get("answer_relevance"),
                created_at=datetime.utcnow()
            )
            await session.execute(stmt)
            await session.commit()
            
            logger.info("Background evaluation scores stored in DB", message_id=message_id, scores=scores)
    except Exception as e:
        logger.error("Failed to store evaluation scores in DB", error=str(e))

