"""
Qdrant hybrid vector store.

* Named dense vector ``dense`` (cosine) + named sparse vector ``sparse`` (IDF modifier).
* Hybrid retrieval uses the Query API: two prefetches fused with Reciprocal Rank Fusion.
* Works against a Qdrant server, a local on-disk path, or fully in-memory (tests).
* Payload filters are built from the backend-agnostic ``RetrievalFilters`` contract.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4

from qdrant_client import AsyncQdrantClient, models

from src.contracts import RetrievalFilters, RetrievedChunk
from src.core.config import settings
from src.core.logger import get_logger

from .sparse_encoder import SparseVectorData

logger = get_logger(__name__)

DENSE = "dense"
SPARSE = "sparse"

_client: Optional[AsyncQdrantClient] = None
_store: Optional["QdrantStore"] = None


def get_qdrant_client() -> AsyncQdrantClient:
    """Process-wide client. In memory mode this *must* be shared so ingestion and search see the same data."""
    global _client
    if _client is None:
        if settings.qdrant_mode == "memory":
            _client = AsyncQdrantClient(":memory:")
        elif settings.qdrant_mode == "path":
            _client = AsyncQdrantClient(path=settings.qdrant_path)
        else:
            _client = AsyncQdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
                api_key=settings.qdrant_api_key,
                timeout=30,
            )
        logger.info("Qdrant client created", mode=settings.qdrant_mode)
    return _client


def get_qdrant_store() -> "QdrantStore":
    global _store
    if _store is None:
        _store = QdrantStore()
    return _store


async def reset_qdrant_for_tests() -> None:
    global _client, _store
    if _client is not None:
        try:
            await _client.close()
        except Exception:
            pass
    _client = None
    _store = None


class QdrantStore:
    def __init__(self, collection: Optional[str] = None, vector_size: Optional[int] = None):
        self.collection = collection or settings.qdrant_collection
        self.vector_size = vector_size or settings.qdrant_vector_size
        self.sparse_enabled = settings.qdrant_sparse_enabled
        self.client = get_qdrant_client()
        self._ready = False
        self._lock = asyncio.Lock()

    # ── Collection management ───────────────────────────────────────────

    async def ensure_collection(self, vector_size: Optional[int] = None) -> None:
        if self._ready:
            return
        async with self._lock:
            if self._ready:
                return
            if vector_size:
                self.vector_size = vector_size
            exists = await self.client.collection_exists(self.collection)
            if not exists:
                sparse_cfg = (
                    {SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)}
                    if self.sparse_enabled else None
                )
                await self.client.create_collection(
                    collection_name=self.collection,
                    vectors_config={
                        DENSE: models.VectorParams(
                            size=self.vector_size,
                            distance=models.Distance.COSINE,
                            on_disk=settings.qdrant_on_disk,
                        )
                    },
                    sparse_vectors_config=sparse_cfg,
                )
                logger.info("Created Qdrant collection", collection=self.collection, dim=self.vector_size)
                await self._create_payload_indexes()
            else:
                info = await self.client.get_collection(self.collection)
                cfg = info.config.params.vectors
                if isinstance(cfg, dict) and DENSE in cfg:
                    existing = cfg[DENSE].size
                    if existing != self.vector_size:
                        logger.warning(
                            "Collection dimension differs from configured; using collection's",
                            collection=self.collection, configured=self.vector_size, existing=existing,
                        )
                        self.vector_size = existing
                else:
                    raise RuntimeError(
                        f"Collection '{self.collection}' was created without the named '{DENSE}' vector. "
                        f"Re-create it (scripts/reset_qdrant.py) to use hybrid search."
                    )
            self._ready = True

    async def _create_payload_indexes(self) -> None:
        if settings.qdrant_mode == "memory":
            return  # local mode ignores payload indexes
        index_specs = {
            "document_id": models.PayloadSchemaType.KEYWORD,
            "tenant_id": models.PayloadSchemaType.KEYWORD,
            "user_id": models.PayloadSchemaType.KEYWORD,
            "content_type": models.PayloadSchemaType.KEYWORD,
            "source": models.PayloadSchemaType.KEYWORD,
            "page": models.PayloadSchemaType.INTEGER,
        }
        for field, schema in index_specs.items():
            try:
                await self.client.create_payload_index(self.collection, field_name=field, field_schema=schema)
            except Exception as exc:  # pragma: no cover - best effort
                logger.warning("Payload index creation failed", field=field, error=str(exc))
        try:
            await self.client.create_payload_index(
                self.collection, field_name="content",
                field_schema=models.TextIndexParams(type="text", tokenizer=models.TokenizerType.WORD, lowercase=True),
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("Full-text index creation failed", error=str(exc))

    # ── Writes ──────────────────────────────────────────────────────────

    async def upsert(
        self,
        payloads: Sequence[Dict[str, Any]],
        dense_vectors: Sequence[Sequence[float]],
        sparse_vectors: Optional[Sequence[SparseVectorData]] = None,
        ids: Optional[Sequence[str]] = None,
    ) -> List[str]:
        if not payloads:
            return []
        await self.ensure_collection(vector_size=len(dense_vectors[0]))
        ids = list(ids) if ids else [str(uuid4()) for _ in payloads]
        points = []
        for i, (pid, payload, dense) in enumerate(zip(ids, payloads, dense_vectors)):
            vector: Dict[str, Any] = {DENSE: list(dense)}
            if self.sparse_enabled and sparse_vectors is not None:
                sv = sparse_vectors[i]
                if not sv.is_empty():
                    vector[SPARSE] = models.SparseVector(indices=sv.indices, values=sv.values)
            points.append(models.PointStruct(id=pid, vector=vector, payload=dict(payload)))
        await self.client.upsert(collection_name=self.collection, points=points, wait=True)
        logger.debug("Upserted points", count=len(points), collection=self.collection)
        return ids

    async def delete_document(self, document_id: str) -> int:
        await self.ensure_collection()
        flt = models.Filter(must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))])
        before = await self.count(document_id=document_id)
        await self.client.delete(collection_name=self.collection, points_selector=models.FilterSelector(filter=flt), wait=True)
        return before

    async def count(self, document_id: Optional[str] = None) -> int:
        await self.ensure_collection()
        flt = None
        if document_id:
            flt = models.Filter(must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))])
        res = await self.client.count(self.collection, count_filter=flt, exact=True)
        return res.count

    # ── Reads ───────────────────────────────────────────────────────────

    @staticmethod
    def build_filter(filters: Optional[RetrievalFilters]) -> Optional[models.Filter]:
        if filters is None or filters.is_empty():
            return None
        must: List[models.Condition] = []
        if filters.document_ids:
            must.append(models.FieldCondition(key="document_id", match=models.MatchAny(any=list(filters.document_ids))))
        if filters.tenant_id:
            must.append(models.FieldCondition(key="tenant_id", match=models.MatchValue(value=filters.tenant_id)))
        if filters.user_id:
            must.append(models.FieldCondition(key="user_id", match=models.MatchValue(value=filters.user_id)))
        if filters.content_types:
            must.append(models.FieldCondition(key="content_type", match=models.MatchAny(any=list(filters.content_types))))
        if filters.page is not None:
            must.append(models.FieldCondition(key="page", match=models.MatchValue(value=int(filters.page))))
        for key, value in (filters.metadata or {}).items():
            if isinstance(value, list):
                must.append(models.FieldCondition(key=key, match=models.MatchAny(any=value)))
            else:
                must.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))
        return models.Filter(must=must) if must else None

    async def hybrid_search(
        self,
        dense_query: Sequence[float],
        sparse_query: Optional[SparseVectorData],
        top_k: int = 10,
        prefetch_k: Optional[int] = None,
        filters: Optional[RetrievalFilters] = None,
    ) -> List[RetrievedChunk]:
        """Dense + sparse prefetch fused by RRF (falls back to dense-only)."""
        await self.ensure_collection()
        prefetch_k = prefetch_k or max(top_k * 3, 20)
        qfilter = self.build_filter(filters)
        started = time.perf_counter()

        use_sparse = self.sparse_enabled and sparse_query is not None and not sparse_query.is_empty()
        if use_sparse:
            prefetch = [
                models.Prefetch(query=list(dense_query), using=DENSE, limit=prefetch_k, filter=qfilter),
                models.Prefetch(
                    query=models.SparseVector(indices=sparse_query.indices, values=sparse_query.values),
                    using=SPARSE, limit=prefetch_k, filter=qfilter,
                ),
            ]
            response = await self.client.query_points(
                collection_name=self.collection,
                prefetch=prefetch,
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=top_k,
                with_payload=True,
            )
        else:
            response = await self.client.query_points(
                collection_name=self.collection,
                query=list(dense_query),
                using=DENSE,
                limit=top_k,
                query_filter=qfilter,
                with_payload=True,
            )

        chunks = [self._to_chunk(p) for p in response.points]
        logger.debug(
            "Qdrant search", hybrid=use_sparse, results=len(chunks),
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        return chunks

    async def dense_search(
        self, dense_query: Sequence[float], top_k: int = 10, filters: Optional[RetrievalFilters] = None,
    ) -> List[RetrievedChunk]:
        return await self.hybrid_search(dense_query, None, top_k=top_k, filters=filters)

    async def get_document_chunks(self, document_id: str, limit: int = 1000) -> List[RetrievedChunk]:
        await self.ensure_collection()
        flt = models.Filter(must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))])
        points, _ = await self.client.scroll(self.collection, scroll_filter=flt, limit=limit, with_payload=True)
        chunks = [self._to_chunk(p) for p in points]
        chunks.sort(key=lambda c: (c.chunk_index or 0))
        return chunks

    @staticmethod
    def _to_chunk(point: Any) -> RetrievedChunk:
        payload = point.payload or {}
        return RetrievedChunk(
            id=str(point.id),
            content=payload.get("raw_content") or payload.get("content", ""),
            score=float(getattr(point, "score", 0.0) or 0.0),
            source=payload.get("source", "unknown"),
            document_id=payload.get("document_id"),
            page=payload.get("page"),
            total_pages=payload.get("total_pages"),
            chunk_index=payload.get("chunk_index"),
            content_type=payload.get("content_type", "text"),
            section_path=payload.get("section_path") or [],
            backend="local",
            metadata={
                k: v for k, v in payload.items()
                if k not in {"content", "raw_content", "source", "document_id", "page", "total_pages",
                             "chunk_index", "content_type", "section_path"}
            },
        )

    # ── Health ──────────────────────────────────────────────────────────

    async def info(self) -> Dict[str, Any]:
        await self.ensure_collection()
        info = await self.client.get_collection(self.collection)
        return {
            "collection": self.collection,
            "points_count": info.points_count,
            "status": str(info.status),
            "vector_size": self.vector_size,
            "sparse_enabled": self.sparse_enabled,
            "mode": settings.qdrant_mode,
        }

    async def healthcheck(self) -> bool:
        try:
            await self.client.get_collections()
            return True
        except Exception as exc:
            logger.warning("Qdrant health check failed", error=str(exc))
            return False
