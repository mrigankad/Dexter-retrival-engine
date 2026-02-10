"""
Memory Service for chat history management.
"""

import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from core.logger import get_logger

logger = get_logger(__name__)


class MemoryService:
    """Chat memory and history management."""
    
    def __init__(self):
        # In-memory storage (replace with PostgreSQL in production)
        self._sessions: Dict[str, List[Dict[str, Any]]] = {}
    
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Add a message to chat history and return its ID."""
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        
        message_id = str(uuid.uuid4())
        message = {
            "id": message_id,
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "metadata": metadata or {},
        }
        
        self._sessions[session_id].append(message)
        logger.debug("Message added", session_id=session_id, role=role, id=message_id)
        return message_id

    
    async def get_history(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get chat history for a session."""
        messages = self._sessions.get(session_id, [])
        return messages[-limit:]
    
    async def get_context_messages(
        self,
        session_id: str,
        limit: int = 10,
    ) -> List[Dict[str, str]]:
        """Get formatted messages for LLM context."""
        messages = await self.get_history(session_id, limit=limit)
        return [{"role": m["role"], "content": m["content"]} for m in messages]
    
    async def clear_history(self, session_id: str) -> None:
        """Clear chat history for a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info("Session cleared", session_id=session_id)
    
    async def summarize_history(
        self,
        session_id: str,
        llm_service: Any = None,
    ) -> str:
        """Summarize chat history (placeholder for long conversations)."""
        messages = await self.get_history(session_id, limit=50)
        if len(messages) < 10:
            return ""
        
        # TODO: Implement summarization using LLM
        return "Previous conversation summary placeholder"
