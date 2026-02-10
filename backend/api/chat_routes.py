"""
Chat routes with SSE streaming support.
"""

import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.config import settings
from core.dependency_injection import CurrentUser, OptionalUser, RateLimited
from core.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


class ChatMessage(BaseModel):
    """Chat message model."""
    role: str = Field(..., description="Message role: user, assistant, or system")
    content: str = Field(..., description="Message content")
    timestamp: Optional[datetime] = None


class ChatRequest(BaseModel):
    """Chat request model."""
    query: str = Field(..., description="User's query", min_length=1, max_length=10000)
    session_id: Optional[str] = Field(None, description="Chat session ID for history")
    chat_history: Optional[List[ChatMessage]] = Field(default=[], description="Previous messages")
    stream: bool = Field(default=True, description="Enable streaming response")
    use_rag: bool = Field(default=True, description="Use RAG retrieval")
    document_ids: Optional[List[str]] = Field(None, description="Scope query to specific documents")


class ChatResponse(BaseModel):
    """Non-streaming chat response model."""
    response: str
    session_id: str
    sources: List[dict] = []
    usage: dict = {}
    route: str = "direct_llm"


class StreamEvent(BaseModel):
    """SSE stream event model."""
    event: str
    data: str


async def generate_sse_response(
    query: str,
    session_id: str,
    use_rag: bool,
    document_ids: Optional[List[str]] = None,
    chat_history: Optional[List[dict]] = None,
    user_id: Optional[str] = None
) -> AsyncGenerator[str, None]:
    """Generate SSE events for streaming chat response."""
    try:
        yield f"event: start\ndata: {session_id}\n\n"
        
        # Import workflow orchestrator
        try:
            from workflow.orchestrator import WorkflowOrchestrator
            orchestrator = WorkflowOrchestrator()
            
            async for event in orchestrator.execute_stream(
                query,
                use_rag,
                session_id=session_id,
                document_ids=document_ids,
                chat_history=chat_history,
                user_id=user_id
            ):
                if event["type"] == "token":
                    yield f"event: token\ndata: {event['data']}\n\n"
                elif event["type"] == "sources":
                    yield f"event: sources\ndata: {json.dumps(event['data'])}\n\n"
                elif event["type"] == "metadata":
                    yield f"event: metadata\ndata: {json.dumps(event['data'])}\n\n"
                elif event["type"] == "context":
                     # Skip context in frontend stream for brevity, 
                     # but kept for reference
                     pass
                elif event["type"] == "error":
                    yield f"event: error\ndata: {event['data']}\n\n"
        
        except ImportError:
            # Fallback for direct LLM
            from services.nvidia_llm_service import NvidiaLLMService
            llm = NvidiaLLMService()
            
            async for token in llm.generate_stream(query, chat_history=chat_history):
                yield f"event: token\ndata: {token}\n\n"
        
        yield f"event: done\ndata: complete\n\n"
        
    except Exception as e:
        logger.exception("Streaming error", error=str(e))
        yield f"event: error\ndata: {str(e)}\n\n"


@router.post("")
async def chat(
    request: ChatRequest,
    http_request: Request,
    user: OptionalUser = None,
):
    """
    Chat endpoint with RAG and streaming support.
    
    Supports both streaming (SSE) and non-streaming responses.
    Uses workflow orchestrator for query routing.
    """
    session_id = request.session_id or f"session_{datetime.utcnow().timestamp()}"
    user_id = user.user_id if user else "anonymous"
    
    # Convert Pydantic models to dicts for internal use
    history_dicts = [m.dict() for m in request.chat_history] if request.chat_history else []

    logger.info(
        "Chat request received",
        session_id=session_id,
        query_length=len(request.query),
        stream=request.stream,
        use_rag=request.use_rag,
        document_ids=request.document_ids,
        user_id=user_id,
    )
    
    if request.stream:
        return StreamingResponse(
            generate_sse_response(
                request.query,
                session_id,
                request.use_rag,
                request.document_ids,
                chat_history=history_dicts,
                user_id=user_id
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Session-ID": session_id,
            },
        )
    
    # Non-streaming response
    try:
        from workflow.orchestrator import WorkflowOrchestrator
        orchestrator = WorkflowOrchestrator()
        result = await orchestrator.execute(
            request.query, 
            request.use_rag, 
            session_id=session_id, 
            document_ids=request.document_ids,
            chat_history=history_dicts,
            user_id=user_id
        )
        
        return ChatResponse(
            response=result["response"],
            session_id=session_id,
            sources=result.get("sources", []),
            usage=result.get("usage", {}),
            route=result.get("route", "direct_llm"),
        )
    except ImportError:
        from services.nvidia_llm_service import NvidiaLLMService
        llm = NvidiaLLMService()
        response = await llm.generate(request.query)
        
        return ChatResponse(
            response=response,
            session_id=session_id,
        )


@router.get("/history/{session_id}")
async def get_chat_history(session_id: str, user: CurrentUser):
    """Get chat history for a session."""
    try:
        from services.memory_service import MemoryService
        memory = MemoryService()
        history = await memory.get_history(session_id, user.user_id)
        return {"session_id": session_id, "messages": history}
    except ImportError:
        return {"session_id": session_id, "messages": []}


@router.delete("/history/{session_id}")
async def clear_chat_history(session_id: str, user: CurrentUser):
    """Clear chat history for a session."""
    logger.info("Clearing chat history", session_id=session_id, user_id=user.user_id)
    return {"status": "cleared", "session_id": session_id}
