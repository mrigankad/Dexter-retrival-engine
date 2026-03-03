"""
NVIDIA NIM Embedding Service.

Provides text embedding generation using NVIDIA's embedding models
with caching, batching, and retry support.
"""

from typing import List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.core.config import settings
from src.core.logger import get_logger, log_timing

logger = get_logger(__name__)


class EmbeddingService:
    """NVIDIA NIM embedding client with caching support."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or settings.nvidia_api_key
        self.base_url = base_url or settings.nvidia_base_url
        self.model = model or settings.nvidia_embed_model
        self.timeout = settings.nvidia_timeout
        self.vector_size = settings.qdrant_vector_size
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        # Simple in-memory cache
        self._cache: dict = {}
    
    def _get_client(self) -> httpx.AsyncClient:
        """Get configured async HTTP client."""
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=httpx.Timeout(self.timeout, connect=10.0),
        )
    
    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        import hashlib
        return hashlib.md5(text.encode()).hexdigest()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    )
    @log_timing("embedding_generate")
    async def embed_text(self, text: str, use_cache: bool = True) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            use_cache: Whether to use caching
            
        Returns:
            List of embedding floats
        """
        if use_cache:
            cache_key = self._get_cache_key(text)
            if cache_key in self._cache:
                logger.debug("Embedding cache hit")
                return self._cache[cache_key]
        
        payload = {
            "model": self.model,
            "input": [text],
            "input_type": "query",
            "encoding_format": "float",
            "truncate": "END",
        }
        
        async with self._get_client() as client:
            response = await client.post("/embeddings", json=payload)
            response.raise_for_status()
            data = response.json()
            
            embedding = data["data"][0]["embedding"]
            
            if use_cache:
                self._cache[cache_key] = embedding
            
            return embedding
    
    @log_timing("batch_embedding_generate")
    async def embed_texts(
        self,
        texts: List[str],
        batch_size: int = 10,
        input_type: str = "passage",
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts with batching.
        
        Args:
            texts: List of texts to embed
            batch_size: Number of texts per API call
            input_type: Type of input (query or passage)
            
        Returns:
            List of embeddings
        """
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            payload = {
                "model": self.model,
                "input": batch,
                "input_type": input_type,
                "encoding_format": "float",
                "truncate": "END",
            }
            
            async with self._get_client() as client:
                response = await client.post("/embeddings", json=payload)
                response.raise_for_status()
                data = response.json()
                
                batch_embeddings = [item["embedding"] for item in data["data"]]
                all_embeddings.extend(batch_embeddings)
            
            logger.debug(f"Processed batch {i // batch_size + 1}", batch_size=len(batch))
        
        logger.info("Batch embedding complete", total_texts=len(texts))
        return all_embeddings
    
    async def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a search query.
        
        Uses query-optimized embedding.
        """
        payload = {
            "model": self.model,
            "input": [query],
            "input_type": "query",
            "encoding_format": "float",
            "truncate": "END",
        }
        
        async with self._get_client() as client:
            response = await client.post("/embeddings", json=payload)
            response.raise_for_status()
            data = response.json()
            
            return data["data"][0]["embedding"]
    
    def clear_cache(self):
        """Clear the embedding cache."""
        self._cache.clear()
        logger.info("Embedding cache cleared")
