"""
Chat Schemas - Request and response models for chat endpoints.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field


class MessageSchema(BaseModel):
    """Chat message schema."""
    role: str = Field(..., description="Message role: user, assistant, system")
    content: str = Field(..., description="Message content")
    timestamp: Optional[datetime] = None


class ChatRequest(BaseModel):
    """Chat request schema."""
    query: str = Field(..., min_length=1, max_length=10000, description="User query")
    session_id: Optional[str] = Field(None, description="Session ID for history")
    chat_history: Optional[List[MessageSchema]] = Field(default=[], description="Previous messages")
    stream: bool = Field(default=True, description="Enable streaming")
    use_rag: bool = Field(default=True, description="Enable RAG retrieval")
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "What is the main topic of the document?",
                "session_id": "session_123",
                "stream": True,
                "use_rag": True,
            }
        }


class SourceSchema(BaseModel):
    """Source document reference schema."""
    title: Optional[str] = None
    source: str
    page: Optional[int] = None
    score: Optional[float] = None
    content_preview: Optional[str] = None


class UsageSchema(BaseModel):
    """Token usage schema."""
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class ChatResponse(BaseModel):
    """Non-streaming chat response schema."""
    response: str = Field(..., description="Generated response")
    session_id: str = Field(..., description="Session ID")
    route: str = Field(default="direct_llm", description="Processing route used")
    sources: List[SourceSchema] = Field(default=[], description="Retrieved sources")
    usage: Optional[UsageSchema] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "response": "Based on the document, the main topic is...",
                "session_id": "session_123",
                "route": "rag_pipeline",
                "sources": [{"source": "document.pdf", "score": 0.92}],
            }
        }


class ChatHistoryResponse(BaseModel):
    """Chat history response schema."""
    session_id: str
    messages: List[MessageSchema]
    total_messages: int


class StreamStartEvent(BaseModel):
    """SSE stream start event."""
    event: str = "start"
    session_id: str


class StreamTokenEvent(BaseModel):
    """SSE stream token event."""
    event: str = "token"
    token: str


class StreamDoneEvent(BaseModel):
    """SSE stream completion event."""
    event: str = "done"
    usage: Optional[UsageSchema] = None
    sources: List[SourceSchema] = []
