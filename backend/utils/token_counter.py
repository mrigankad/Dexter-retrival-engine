"""
Token Counter - Utilities for token counting and budget management.
"""

from typing import List, Optional

from core.logger import get_logger

logger = get_logger(__name__)


class TokenCounter:
    """Token counting utilities using tiktoken."""
    
    def __init__(self, model: str = "gpt-4"):
        """
        Initialize token counter.
        
        Args:
            model: Model name for tokenizer selection
        """
        self.model = model
        self._encoder = None
    
    @property
    def encoder(self):
        """Lazy load tokenizer."""
        if self._encoder is None:
            try:
                import tiktoken
                self._encoder = tiktoken.get_encoding("cl100k_base")
            except ImportError:
                logger.warning("tiktoken not available, using approximate counting")
                self._encoder = None
        return self._encoder
    
    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Token count
        """
        if self.encoder:
            return len(self.encoder.encode(text))
        
        # Fallback: approximate 4 chars per token
        return len(text) // 4
    
    def count_messages_tokens(self, messages: List[dict]) -> int:
        """
        Count tokens in a list of chat messages.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            
        Returns:
            Total token count
        """
        total = 0
        
        for message in messages:
            # Base tokens per message (approx)
            total += 4
            
            for key, value in message.items():
                if isinstance(value, str):
                    total += self.count_tokens(value)
        
        return total
    
    def truncate_to_tokens(
        self,
        text: str,
        max_tokens: int,
        suffix: str = "...",
    ) -> str:
        """
        Truncate text to fit within token budget.
        
        Args:
            text: Text to truncate
            max_tokens: Maximum tokens allowed
            suffix: Suffix to add if truncated
            
        Returns:
            Truncated text
        """
        tokens = self.count_tokens(text)
        
        if tokens <= max_tokens:
            return text
        
        # Binary search for truncation point
        suffix_tokens = self.count_tokens(suffix)
        target_tokens = max_tokens - suffix_tokens
        
        # Approximate character position
        ratio = target_tokens / tokens
        char_pos = int(len(text) * ratio)
        
        # Adjust to word boundary
        truncated = text[:char_pos].rsplit(" ", 1)[0]
        
        return truncated + suffix
    
    def estimate_cost(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        model: Optional[str] = None,
    ) -> float:
        """
        Estimate API cost based on token usage.
        
        Args:
            prompt_tokens: Input tokens
            completion_tokens: Output tokens
            model: Model name (affects pricing)
            
        Returns:
            Estimated cost in USD
        """
        # Approximate pricing (update as needed)
        pricing = {
            "default": {"input": 0.01, "output": 0.03},  # per 1K tokens
        }
        
        rate = pricing.get(model or "default", pricing["default"])
        
        cost = (
            (prompt_tokens / 1000) * rate["input"] +
            (completion_tokens / 1000) * rate["output"]
        )
        
        return round(cost, 6)


# Singleton instance
token_counter = TokenCounter()
