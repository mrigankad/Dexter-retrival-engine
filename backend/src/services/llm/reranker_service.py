"""
Open-Source Local Reranker Service.

Uses sentence-transformers CrossEncoder for reranking.
Runs locally — no API key required, no external calls.

Model: cross-encoder/ms-marco-MiniLM-L-6-v2 (lightweight, fast)
Alternative: BAAI/bge-reranker-v2-m3 (higher quality, multilingual)
"""

import asyncio
from typing import List, Tuple, Optional
from functools import lru_cache

from src.core.config import settings
from src.core.logger import get_logger, log_timing

logger = get_logger(__name__)

# Default model - lightweight and fast (~80MB)
DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@lru_cache(maxsize=1)
def _load_cross_encoder(model_name: str):
    """Load and cache the CrossEncoder model (singleton)."""
    from sentence_transformers import CrossEncoder

    logger.info("Loading CrossEncoder reranker model", model=model_name)
    model = CrossEncoder(model_name)
    logger.info("CrossEncoder reranker model loaded", model=model_name)
    return model


class RerankerService:
    """Local open-source reranker using CrossEncoder."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        **kwargs,  # Accept and ignore legacy kwargs (api_key, base_url, etc.)
    ):
        self.model_name = model_name or DEFAULT_MODEL
        self._model = None

    def _get_model(self):
        """Lazy-load the CrossEncoder model."""
        if self._model is None:
            self._model = _load_cross_encoder(self.model_name)
        return self._model

    @log_timing("rerank")
    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: Optional[int] = None,
    ) -> List[Tuple[int, str, float]]:
        """
        Rerank documents by relevance to query using a local CrossEncoder.

        Args:
            query: Search query
            documents: List of document texts
            top_k: Number of top results to return

        Returns:
            List of (original_index, document, score) tuples, sorted by score desc
        """
        if not documents:
            return []

        top_k = top_k or getattr(settings, "rerank_top_k", 8)

        try:
            model = self._get_model()

            # Build query-document pairs for CrossEncoder
            pairs = [(query, doc) for doc in documents]

            # Run scoring in a thread pool to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            scores = await loop.run_in_executor(
                None, lambda: model.predict(pairs).tolist()
            )

            # Build scored results
            scored = [
                (i, documents[i], float(scores[i]))
                for i in range(len(documents))
            ]

            # Sort by score descending
            scored.sort(key=lambda x: x[2], reverse=True)

            # Return top_k
            results = scored[:top_k]

            logger.info(
                "Reranking complete (local CrossEncoder)",
                model=self.model_name,
                query_length=len(query),
                input_docs=len(documents),
                output_docs=len(results),
                top_score=round(results[0][2], 4) if results else 0,
            )

            return results

        except Exception as e:
            logger.error(
                f"Local reranking failed: {str(e)}. Falling back to original order.",
                model=self.model_name,
            )
            # Fallback: return original order with 0.0 score
            return [(i, doc, 0.0) for i, doc in enumerate(documents[:top_k])]

    async def rerank_with_metadata(
        self,
        query: str,
        documents: List[dict],
        text_key: str = "content",
        top_k: Optional[int] = None,
    ) -> List[dict]:
        """
        Rerank documents with metadata preservation.

        Args:
            query: Search query
            documents: List of document dicts with text and metadata
            text_key: Key containing the text content
            top_k: Number of top results

        Returns:
            Reranked documents with scores added
        """
        texts = [doc[text_key] for doc in documents]

        rankings = await self.rerank(query, texts, top_k)

        results = []
        for idx, _, score in rankings:
            doc = documents[idx].copy()
            doc["rerank_score"] = score
            results.append(doc)

        return results
