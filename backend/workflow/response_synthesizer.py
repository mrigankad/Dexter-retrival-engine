"""
Response Synthesizer - Builds prompts and formats responses.
"""

from typing import List, Dict, Optional

from core.logger import get_logger

logger = get_logger(__name__)


class ResponseSynthesizer:
    """Synthesizes prompts and formats responses for LLM."""
    
    def __init__(self, max_context_tokens: int = 4096):
        self.max_context_tokens = max_context_tokens
    
    def build_rag_prompt(
        self,
        query: str,
        context_chunks: List[Dict],
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Build a RAG prompt with context.
        
        Args:
            query: User query
            context_chunks: Retrieved context chunks
            system_prompt: Optional system instructions
            
        Returns:
            Formatted prompt string
        """
        if not context_chunks:
            return query
        
        # Format context with page numbers
        context_parts = []
        for i, chunk in enumerate(context_chunks, 1):
            content = chunk.get("payload", {}).get("content", chunk.get("content", ""))
            source = chunk.get("payload", {}).get("source", "Unknown")
            page = chunk.get("payload", {}).get("page", "N/A")
            total_pages = chunk.get("payload", {}).get("total_pages", "N/A")
            
            if page != "N/A":
                context_parts.append(f"[{i}] Source: {source}, Page {page}/{total_pages}\n{content}")
            else:
                context_parts.append(f"[{i}] Source: {source}\n{content}")
        
        context_str = "\n\n".join(context_parts)
        
        prompt = f"""Based on the following context, answer the question. When citing information, always include the source name and page number in your response.

CONTEXT:
{context_str}

QUESTION: {query}

ANSWER (include page references for key facts):"""
        
        return prompt
    
    def build_chat_prompt(
        self,
        query: str,
        chat_history: List[Dict[str, str]],
        max_history: int = 10,
    ) -> List[Dict[str, str]]:
        """
        Build chat messages with history.
        
        Args:
            query: Current user query
            chat_history: Previous messages
            max_history: Maximum history messages to include
            
        Returns:
            List of message dicts for API
        """
        messages = chat_history[-max_history:] if chat_history else []
        messages.append({"role": "user", "content": query})
        return messages
    
    def format_sources(self, chunks: List[Dict]) -> List[Dict]:
        """Format source metadata for response."""
        sources = []
        for chunk in chunks:
            payload = chunk.get("payload", {})
            sources.append({
                "title": payload.get("title", "Unknown"),
                "source": payload.get("source", "Unknown"),
                "page": payload.get("page"),
                "score": chunk.get("score"),
            })
        return sources
    
    def truncate_context(self, text: str, max_chars: int = 12000) -> str:
        """Truncate context to fit token budget."""
        if len(text) <= max_chars:
            return text
        
        return text[:max_chars] + "\n\n[Context truncated...]"
