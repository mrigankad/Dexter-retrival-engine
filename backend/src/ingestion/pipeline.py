"""
Ingestion pipeline: parse → chunk → embed (dense + sparse) → Qdrant → DB records.

Optional enrichment steps (knowledge graph, object storage) are feature-flagged
and never block indexing.
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select, update

from src.contracts import Chunk, IngestionJob, IngestionResult
from src.core.config import settings
from src.core.logger import get_logger
from src.infrastructure.database import Document, DocumentChunk, session_scope
from src.infrastructure.vector_store import SparseEncoder, get_qdrant_store
from src.services.llm.embedding_service import EmbeddingService, get_embedding_service

from .chunker import HierarchicalChunker
from .parsers import parse_file

logger = get_logger(__name__)


class IngestionPipeline:
    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        store=None,
        chunker: Optional[HierarchicalChunker] = None,
        persist_db: bool = True,
    ):
        self._embedding = embedding_service
        self._store = store
        self.chunker = chunker or HierarchicalChunker()
        self.sparse = SparseEncoder()
        self.persist_db = persist_db

    @property
    def embedding(self) -> EmbeddingService:
        if self._embedding is None:
            self._embedding = get_embedding_service()
        return self._embedding

    @property
    def store(self):
        if self._store is None:
            self._store = get_qdrant_store()
        return self._store

    # ── main entry ─────────────────────────────────────────────────────

    async def process(self, job: IngestionJob) -> IngestionResult:
        started = time.perf_counter()
        document_id = job.document_id
        await self._set_status(document_id, "processing")
        try:
            doc = parse_file(job.file_path)
            doc.filename = job.filename or doc.filename   # cite the original name, not the on-disk UUID
            chunks = self.chunker.chunk_document(doc, document_id)
            if not chunks:
                raise RuntimeError("Document produced no chunks")

            await self._index_chunks(chunks, job)
            if self.persist_db:
                await self._record_chunks(document_id, chunks)

            stats: Dict[str, Any] = {
                "parser": doc.parser,
                "pages": doc.total_pages,
                "chunks": len(chunks),
                "table_chunks": sum(1 for c in chunks if c.content_type.value == "table"),
                "avg_tokens": round(sum(c.token_estimate for c in chunks) / len(chunks)),
            }
            await self._enrich(doc, chunks, job, stats)

            duration = round((time.perf_counter() - started) * 1000, 1)
            await self._set_status(document_id, "completed", chunks_count=len(chunks), total_pages=doc.total_pages,
                                   metadata={**stats, "duration_ms": duration, "title": doc.title})
            logger.info("Document indexed", document_id=document_id, **stats, duration_ms=duration)
            return IngestionResult(document_id=document_id, status="completed", chunks_count=len(chunks),
                                   total_pages=doc.total_pages, parser=doc.parser, duration_ms=duration, stats=stats)
        except Exception as exc:
            logger.exception("Ingestion failed", document_id=document_id, error=str(exc))
            await self._set_status(document_id, "failed", error=str(exc))
            return IngestionResult(document_id=document_id, status="failed", error=str(exc),
                                   duration_ms=round((time.perf_counter() - started) * 1000, 1))
        finally:
            if job.metadata.get("delete_after", False) and os.path.exists(job.file_path):
                try:
                    os.remove(job.file_path)
                except OSError:
                    pass

    # ── steps ──────────────────────────────────────────────────────────

    async def _index_chunks(self, chunks: List[Chunk], job: IngestionJob) -> None:
        batch = settings.embedding_batch_size
        for start in range(0, len(chunks), batch):
            part = chunks[start:start + batch]
            texts = [c.content for c in part]
            dense = await self.embedding.embed_texts(texts, input_type="passage")
            sparse = self.sparse.encode_documents(texts)
            payloads = []
            for c in part:
                payloads.append({
                    "document_id": c.document_id,
                    "source": c.source,
                    "content": c.content,
                    "raw_content": c.raw_content,
                    "page": c.page,
                    "total_pages": c.total_pages,
                    "chunk_index": c.chunk_index,
                    "content_type": c.content_type.value,
                    "chunk_level": c.chunk_level.value,
                    "section_path": c.section_path,
                    "title": c.metadata.get("title"),
                    "tenant_id": job.tenant_id,
                    "user_id": job.user_id,
                    "visibility": job.visibility,
                    "acl": list(job.acl) or ["public"],
                    "token_estimate": c.token_estimate,
                    **{k: v for k, v in job.metadata.items() if isinstance(v, (str, int, float, bool))},
                })
            await self.store.upsert(payloads, dense, sparse, ids=[c.id for c in part])

    async def _record_chunks(self, document_id: str, chunks: List[Chunk]) -> None:
        doc_uuid = uuid.UUID(document_id)
        async with session_scope() as session:
            await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc_uuid))
            for c in chunks:
                session.add(DocumentChunk(
                    document_id=doc_uuid, chunk_index=c.chunk_index, content=c.raw_content, vector_id=c.id,
                    page=c.page, content_type=c.content_type.value, chunk_level=c.chunk_level.value,
                    word_count=len(c.raw_content.split()), chunk_metadata={"section_path": c.section_path},
                ))

    async def _enrich(self, doc, chunks: List[Chunk], job: IngestionJob, stats: Dict[str, Any]) -> None:
        if settings.enable_object_storage:
            try:
                from src.services.llm.object_storage_service import ObjectStorageService
                ObjectStorageService().upload_file(
                    file_path=job.file_path, bucket_name=settings.minio_bucket_documents,
                    object_name=f"{job.document_id}/{job.filename}", metadata={"document_id": job.document_id},
                )
                stats["archived"] = True
            except Exception as exc:
                logger.warning("Object storage archive failed", error=str(exc))
        if settings.enable_knowledge_graph:
            try:
                from src.services.llm.graph_extraction_service import GraphExtractionService
                from src.services.llm.knowledge_graph_service import KnowledgeGraphService
                from src.services.llm.nvidia_llm_service import get_llm_service
                graph = KnowledgeGraphService()
                extractor = GraphExtractionService(llm_service=get_llm_service())
                total = 0
                for c in chunks[:200]:
                    if c.content_type.value != "text":
                        continue
                    for t in await extractor.extract_triplets(c.raw_content):
                        graph.add_triplet(t["subject"], t["relation"], t["object"], job.document_id, {"source": c.source})
                        total += 1
                stats["graph_triplets"] = total
            except Exception as exc:
                logger.warning("Knowledge graph extraction failed", error=str(exc))

    async def _set_status(self, document_id: str, status: str, chunks_count: Optional[int] = None,
                          total_pages: Optional[int] = None, error: Optional[str] = None,
                          metadata: Optional[Dict[str, Any]] = None) -> None:
        if not self.persist_db:
            return
        try:
            values: Dict[str, Any] = {"status": status}
            if chunks_count is not None:
                values["chunks_count"] = chunks_count
            if total_pages is not None:
                values["total_pages"] = total_pages
            if error is not None:
                values["error_message"] = error[:2000]
            if status == "completed":
                values["processed_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
            async with session_scope() as session:
                if metadata:
                    # merge: keep provenance written by uploads/connectors (url, connector, owner, ...)
                    doc = await session.get(Document, uuid.UUID(document_id))
                    existing = dict(doc.doc_metadata or {}) if doc is not None else {}
                    values["doc_metadata"] = {**existing, **metadata}
                await session.execute(update(Document).where(Document.id == uuid.UUID(document_id)).values(**values))
        except Exception as exc:
            logger.warning("Could not update document status", document_id=document_id, error=str(exc))

    # ── deletion ───────────────────────────────────────────────────────

    async def delete_document(self, document_id: str) -> Dict[str, Any]:
        removed = await self.store.delete_document(document_id)
        if self.persist_db:
            async with session_scope() as session:
                await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == uuid.UUID(document_id)))
        return {"document_id": document_id, "vectors_removed": removed}


_default: Optional[IngestionPipeline] = None


def get_ingestion_pipeline() -> IngestionPipeline:
    global _default
    if _default is None:
        _default = IngestionPipeline()
    return _default


def reset_ingestion_pipeline() -> None:
    global _default
    _default = None
