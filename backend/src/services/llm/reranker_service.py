"""
Reranker with three backends.

* ``nvidia`` – NIM reranking endpoint (llama-3.2-nv-rerankqa-1b-v2). Default: no local model.
* ``local``  – sentence-transformers CrossEncoder (optional dependency).
* ``none``   – keep fusion order.

The public API returns ``(original_index, document, score)`` tuples so callers
can map scores back to full chunk objects.
"""

from __future__ import annotations

import asyncio
import math
from typing import List, Optional, Tuple

import httpx

from src.core.config import settings
from src.core.logger import get_logger, log_timing

logger = get_logger(__name__)

Ranking = Tuple[int, str, float]


def _sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


class RerankerService:
    _shared_client: Optional[httpx.AsyncClient] = None

    def __init__(self, backend: Optional[str] = None, model_name: Optional[str] = None, **_: object):
        self.backend = backend or settings.reranker_backend
        self.model_name = model_name or (
            settings.nvidia_rerank_model if self.backend == "nvidia" else settings.local_reranker_model
        )
        self._local_model = None

    # ── NVIDIA NIM ──────────────────────────────────────────────────────

    def _client(self) -> httpx.AsyncClient:
        cls = type(self)
        if cls._shared_client is None or cls._shared_client.is_closed:
            cls._shared_client = httpx.AsyncClient(
                headers={"Authorization": f"Bearer {settings.nvidia_api_key}", "Content-Type": "application/json", "Accept": "application/json"},
                timeout=httpx.Timeout(settings.nvidia_timeout, connect=10.0),
            )
        return cls._shared_client

    @classmethod
    async def aclose(cls) -> None:
        if cls._shared_client is not None and not cls._shared_client.is_closed:
            await cls._shared_client.aclose()
        cls._shared_client = None

    async def _rerank_nvidia(self, query: str, documents: List[str]) -> List[Ranking]:
        payload = {
            "model": self.model_name,
            "query": {"text": query[:4000]},
            "passages": [{"text": d[:6000]} for d in documents],
            "truncate": "END",
        }
        response = await self._client().post(settings.nvidia_rerank_url, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(f"Rerank API error {response.status_code}: {response.text[:300]}")
        rankings = response.json().get("rankings", [])
        out: List[Ranking] = []
        for r in rankings:
            idx = int(r["index"])
            score = float(r.get("logit", r.get("score", 0.0)))
            out.append((idx, documents[idx], _sigmoid(score)))
        return out

    # ── Local CrossEncoder ──────────────────────────────────────────────

    def _get_local_model(self):
        if self._local_model is None:
            from sentence_transformers import CrossEncoder  # optional dependency
            logger.info("Loading local reranker", model=self.model_name)
            self._local_model = CrossEncoder(self.model_name)
        return self._local_model

    async def _rerank_local(self, query: str, documents: List[str]) -> List[Ranking]:
        model = self._get_local_model()
        pairs = [(query, d) for d in documents]
        scores = await asyncio.get_running_loop().run_in_executor(None, lambda: model.predict(pairs).tolist())
        return [(i, documents[i], _sigmoid(float(scores[i]))) for i in range(len(documents))]

    # ── Public API ──────────────────────────────────────────────────────

    @log_timing("rerank")
    async def rerank(self, query: str, documents: List[str], top_k: Optional[int] = None) -> List[Ranking]:
        if not documents:
            return []
        top_k = top_k or settings.rerank_top_k
        if self.backend == "none" or len(documents) == 1:
            return [(i, d, 0.0) for i, d in enumerate(documents[:top_k])]
        try:
            if self.backend == "local":
                scored = await self._rerank_local(query, documents)
            else:
                scored = await self._rerank_nvidia(query, documents)
        except Exception as exc:
            logger.warning("Reranking failed; keeping fusion order", backend=self.backend, error=str(exc))
            return [(i, d, 0.0) for i, d in enumerate(documents[:top_k])]
        scored.sort(key=lambda t: t[2], reverse=True)
        return scored[:top_k]

    async def rerank_with_metadata(self, query: str, documents: List[dict], text_key: str = "content", top_k: Optional[int] = None) -> List[dict]:
        rankings = await self.rerank(query, [d[text_key] for d in documents], top_k)
        out = []
        for idx, _, score in rankings:
            doc = dict(documents[idx])
            doc["rerank_score"] = score
            out.append(doc)
        return out


_default: Optional[RerankerService] = None


def get_reranker_service() -> RerankerService:
    global _default
    if _default is None:
        _default = RerankerService()
    return _default


def set_reranker_service(service: Optional[RerankerService]) -> None:
    global _default
    _default = service
