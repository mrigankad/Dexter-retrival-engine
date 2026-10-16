"""
NVIDIA NIM embedding client with batching, retries and an LRU cache.

Asymmetric models (nv-embedqa) need ``input_type`` = ``query`` for questions and
``passage`` for documents; this service always sets it correctly.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from typing import List, Optional

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core.config import settings
from src.core.logger import get_logger, log_timing

logger = get_logger(__name__)


class EmbeddingError(RuntimeError):
    pass


class EmbeddingService:
    _shared_client: Optional[httpx.AsyncClient] = None

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        dimensions: Optional[int] = None,
    ):
        self.api_key = api_key or settings.nvidia_api_key
        self.base_url = base_url or settings.nvidia_base_url
        self.model = model or settings.nvidia_embed_model
        self.dimensions = dimensions or settings.nvidia_embed_dimensions
        self.timeout = settings.nvidia_timeout
        self.batch_size = settings.embedding_batch_size
        self._cache: "OrderedDict[str, List[float]]" = OrderedDict()
        self._cache_size = settings.embedding_cache_size

    def _client(self) -> httpx.AsyncClient:
        cls = type(self)
        if cls._shared_client is None or cls._shared_client.is_closed:
            cls._shared_client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                timeout=httpx.Timeout(self.timeout, connect=10.0),
            )
        return cls._shared_client

    @classmethod
    async def aclose(cls) -> None:
        if cls._shared_client is not None and not cls._shared_client.is_closed:
            await cls._shared_client.aclose()
        cls._shared_client = None

    @staticmethod
    def _key(text: str, input_type: str) -> str:
        return hashlib.sha1(f"{input_type}:{text}".encode("utf-8")).hexdigest()

    def _cache_get(self, key: str) -> Optional[List[float]]:
        vec = self._cache.get(key)
        if vec is not None:
            self._cache.move_to_end(key)
        return vec

    def _cache_put(self, key: str, vec: List[float]) -> None:
        self._cache[key] = vec
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    async def _embed_batch(self, texts: List[str], input_type: str) -> List[List[float]]:
        if not self.api_key:
            raise EmbeddingError("NVIDIA_API_KEY is not configured")
        payload = {
            "model": self.model,
            "input": texts,
            "input_type": input_type,
            "encoding_format": "float",
            "truncate": "END",
        }
        if self.dimensions:
            payload["dimensions"] = self.dimensions
        response = await self._client().post("/embeddings", json=payload)
        if response.status_code >= 400:
            raise EmbeddingError(f"Embedding API error {response.status_code}: {response.text[:300]}")
        data = response.json()["data"]
        data.sort(key=lambda d: d.get("index", 0))
        return [item["embedding"] for item in data]

    @log_timing("embed_texts")
    async def embed_texts(self, texts: List[str], input_type: str = "passage", batch_size: Optional[int] = None) -> List[List[float]]:
        """Embed many texts (documents by default) with batching + cache."""
        if not texts:
            return []
        batch_size = batch_size or self.batch_size
        results: List[Optional[List[float]]] = [None] * len(texts)
        pending: List[int] = []
        for i, text in enumerate(texts):
            cached = self._cache_get(self._key(text, input_type))
            if cached is not None:
                results[i] = cached
            else:
                pending.append(i)
        for start in range(0, len(pending), batch_size):
            idxs = pending[start:start + batch_size]
            vectors = await self._embed_batch([texts[i] for i in idxs], input_type)
            for i, vec in zip(idxs, vectors):
                results[i] = vec
                self._cache_put(self._key(texts[i], input_type), vec)
        return [r for r in results if r is not None]

    async def embed_query(self, query: str) -> List[float]:
        return (await self.embed_texts([query], input_type="query"))[0]

    async def embed_queries(self, queries: List[str]) -> List[List[float]]:
        return await self.embed_texts(queries, input_type="query")

    async def embed_text(self, text: str, use_cache: bool = True) -> List[float]:
        """Backward-compatible single-passage embed."""
        return (await self.embed_texts([text], input_type="passage"))[0]

    def clear_cache(self) -> None:
        self._cache.clear()


_default: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    global _default
    if _default is None:
        _default = EmbeddingService()
    return _default


def set_embedding_service(service: Optional[EmbeddingService]) -> None:
    global _default
    _default = service
