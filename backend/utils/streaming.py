"""
Streaming Utilities - SSE and streaming response helpers.
"""

import asyncio
import json
from typing import AsyncGenerator, Any, Optional

from core.logger import get_logger

logger = get_logger(__name__)


class SSEFormatter:
    """Server-Sent Events formatter."""
    
    @staticmethod
    def format_event(event: str, data: Any, event_id: Optional[str] = None) -> str:
        """
        Format an SSE event.
        
        Args:
            event: Event type name
            data: Event data (will be JSON encoded if dict)
            event_id: Optional event ID
            
        Returns:
            Formatted SSE string
        """
        lines = []
        
        if event_id:
            lines.append(f"id: {event_id}")
        
        lines.append(f"event: {event}")
        
        if isinstance(data, dict):
            data = json.dumps(data)
        
        lines.append(f"data: {data}")
        lines.append("")  # Empty line to end event
        
        return "\n".join(lines) + "\n"
    
    @staticmethod
    def format_token(token: str) -> str:
        """Format a token event for streaming."""
        return f"event: token\ndata: {token}\n\n"
    
    @staticmethod
    def format_start(session_id: str) -> str:
        """Format stream start event."""
        return f"event: start\ndata: {session_id}\n\n"
    
    @staticmethod
    def format_done(metadata: Optional[dict] = None) -> str:
        """Format stream completion event."""
        data = json.dumps(metadata) if metadata else "complete"
        return f"event: done\ndata: {data}\n\n"
    
    @staticmethod
    def format_error(error: str) -> str:
        """Format error event."""
        return f"event: error\ndata: {error}\n\n"


async def stream_with_timeout(
    generator: AsyncGenerator[str, None],
    timeout_seconds: float = 60.0,
) -> AsyncGenerator[str, None]:
    """
    Wrap a generator with timeout protection.
    
    Args:
        generator: Async generator to wrap
        timeout_seconds: Timeout for each token
        
    Yields:
        Tokens from the generator
    """
    try:
        async for token in generator:
            try:
                yield token
            except asyncio.CancelledError:
                logger.info("Stream cancelled by client")
                break
    except asyncio.TimeoutError:
        logger.warning("Stream timeout")
        yield SSEFormatter.format_error("Stream timeout")
    except Exception as e:
        logger.exception("Stream error", error=str(e))
        yield SSEFormatter.format_error(str(e))


async def buffer_tokens(
    generator: AsyncGenerator[str, None],
    buffer_size: int = 5,
    flush_interval: float = 0.1,
) -> AsyncGenerator[str, None]:
    """
    Buffer tokens for smoother streaming.
    
    Args:
        generator: Token generator
        buffer_size: Number of tokens to buffer
        flush_interval: Max time before flush
        
    Yields:
        Buffered tokens
    """
    buffer = []
    last_flush = asyncio.get_event_loop().time()
    
    async for token in generator:
        buffer.append(token)
        current_time = asyncio.get_event_loop().time()
        
        if len(buffer) >= buffer_size or (current_time - last_flush) >= flush_interval:
            yield "".join(buffer)
            buffer = []
            last_flush = current_time
    
    if buffer:
        yield "".join(buffer)
