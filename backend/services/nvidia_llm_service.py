"""
NVIDIA NIM LLM Service with streaming support.

Provides async integration with NVIDIA NIM APIs for text generation
with retry logic, timeout management, and streaming responses.
"""

import asyncio
from typing import AsyncGenerator, Dict, List, Optional, Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from core.config import settings
from core.logger import get_logger, log_timing

logger = get_logger(__name__)


class NvidiaLLMService:
    """NVIDIA NIM LLM client with streaming support."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or settings.nvidia_api_key
        self.base_url = base_url or settings.nvidia_base_url
        self.model = model or settings.nvidia_llm_model
        self.timeout = settings.nvidia_timeout
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
    
    def _get_client(self) -> httpx.AsyncClient:
        """Get configured async HTTP client."""
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=httpx.Timeout(self.timeout, connect=10.0),
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    )
    @log_timing("llm_generate")
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        """
        Generate text completion (non-streaming).
        
        Args:
            prompt: User prompt
            system_prompt: System instructions
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            top_p: Top-p sampling
            
        Returns:
            Generated text response
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": False,
        }
        
        async with self._get_client() as client:
            response = await client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            
            return data["choices"][0]["message"]["content"]
    
    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        chat_history: Optional[List[Dict[str, str]]] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> AsyncGenerator[str, None]:
        """
        Generate streaming text completion.
        
        Args:
            prompt: User prompt
            system_prompt: System instructions
            chat_history: Previous conversation messages
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            top_p: Top-p sampling
            
        Yields:
            Text tokens as they are generated
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        if chat_history:
            messages.extend(chat_history)
        
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": True,
        }
        
        logger.info("Starting streaming generation", model=self.model, prompt_length=len(prompt))
        
        try:
            async with self._get_client() as client:
                async with client.stream("POST", "/chat/completions", json=payload) as response:
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            
                            try:
                                import json
                                data = json.loads(data_str)
                                delta = data.get("choices", [{}])[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                            except Exception:
                                continue
                                
        except httpx.TimeoutException:
            logger.error("Streaming timeout")
            raise
        except Exception as e:
            logger.exception("Streaming error", error=str(e))
            raise
    
    async def generate_with_context(
        self,
        query: str,
        context: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> AsyncGenerator[str, None]:
        """
        Generate response with RAG context.
        
        Args:
            query: User query
            context: Retrieved context from vector store
            system_prompt: System instructions
            max_tokens: Maximum tokens to generate
            
        Yields:
            Text tokens as they are generated
        """
        default_system = """You are a helpful AI assistant. Answer the user's question based on the provided context.
If the context doesn't contain relevant information, say so and provide a general answer.
Always be accurate and cite the context when relevant."""
        
        full_prompt = f"""Context:
{context}

Question: {query}

Answer:"""
        
        async for token in self.generate_stream(
            prompt=full_prompt,
            system_prompt=system_prompt or default_system,
            max_tokens=max_tokens,
        ):
            yield token
