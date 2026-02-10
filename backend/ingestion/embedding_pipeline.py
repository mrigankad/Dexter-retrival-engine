"""
Embedding Pipeline - Enterprise-Grade Ingestion with Multimodal Support.

Pipeline:
1. Archival (MinIO)
2. Parsing (Docling → Marker → PyMuPDF fallback)
3. Content Routing (text / table / chart / image)
4. Table Canonicalization
5. Chart Analysis
6. Hierarchical Chunking
7. Batch Embedding
8. Vector Upsert
"""

from typing import List, Dict, Any, Optional
import os
import asyncio

from core.config import settings
from core.logger import get_logger, log_timing
from services.document_parser_service import DocumentParserService
from services.embedding_service import EmbeddingService
from services.vector_store_service import VectorStoreService
from services.object_storage_service import ObjectStorageService
from services.multimodal_parser_service import MultimodalParserService

from .chunking_strategy import ChunkingStrategy, ParagraphChunker
from .content_router import ContentRouter
from .table_canonicalizer import TableCanonicalizer
from .chart_analyzer import ChartAnalyzer

logger = get_logger(__name__)


class EmbeddingPipeline:
    """Production Ingestion Pipeline with multimodal content routing."""

    def __init__(self, llm_service=None):
        self.parser = DocumentParserService()
        self.chunker = ParagraphChunker()
        self.embedding_service = EmbeddingService()
        self.vector_store = VectorStoreService()
        self.object_storage = ObjectStorageService()
        self.multimodal_parser = MultimodalParserService()

        # ── New Production Components ──
        self.content_router = ContentRouter(llm_service=llm_service)
        self.table_canonicalizer = TableCanonicalizer()
        self.chart_analyzer = ChartAnalyzer(llm_service=llm_service)

    @log_timing("document_pipeline")
    async def process_document(
        self,
        document_id: str,
        file_path: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Process a document through the full Enterprise Ingestion Pipeline.

        Layers:
        1. Immutable Archival (MinIO)
        2. Parsing (Docling / Marker / PyMuPDF)
        3. Content Routing (Table Canonicalization + Chart Analysis)
        4. Hierarchical Chunking (Section → Paragraph → Data)
        5. Knowledge Graph Extraction (Subject-Predicate-Object triplets)
        6. Batch Embedding + Vector Upsert
        """
        metadata = metadata or {}
        filename = os.path.basename(file_path)

        logger.info("Starting Enterprise Ingestion", document_id=document_id, file=filename)

        # Step 1: Immutable Archival (MinIO)
        try:
            object_name = f"{document_id}/{filename}"
            self.object_storage.upload_file(
                file_path=file_path,
                bucket_name=settings.minio_bucket_documents,
                object_name=object_name,
                metadata={"document_id": document_id, **metadata}
            )
        except Exception as e:
            logger.error("MinIO upload failed", error=str(e))

        # Step 2: Advanced Parsing (Docling + Multimodal)
        parsed_document = await self.multimodal_parser.process_document(file_path)

        # Step 3: Content Routing (Table Canonicalization + Chart Analysis)
        routed_content = await self.content_router.route_and_process(
            parsed_document=parsed_document,
            document_id=document_id,
            filename=filename,
            metadata=metadata,
        )

        logger.info(
            "Content routing complete",
            stats=routed_content.get("processing_stats", {}),
        )

        # Step 4: Hierarchical Chunking
        all_chunks = self._create_hierarchical_chunks(
            routed_content, document_id, filename, metadata
        )

        if not all_chunks:
            logger.error("No indexable content found", document_id=document_id)
            return {"status": "error", "message": "No content"}

        logger.info("Content chunked", count=len(all_chunks))

        # Step 5: Knowledge Graph Extraction
        from services.knowledge_graph_service import KnowledgeGraphService
        from services.graph_extraction_service import GraphExtractionService
        from services.nvidia_llm_service import NvidiaLLMService
        
        llm = NvidiaLLMService()
        graph_service = KnowledgeGraphService()
        extractor = GraphExtractionService(llm_service=llm)
        
        # Parallel extraction for important chunks (summary and deep paragraphs)
        graph_tasks = []
        if all_chunks:
            logger.info("DEBUG: First chunk detail", 
                        content_type=all_chunks[0].get("content_type"),
                        chunk_level=all_chunks[0].get("chunk_level"))
        
        for chunk in all_chunks:
            # Fix: Check content_type and chunk_level correctly
            is_text = chunk.get("content_type") == "text"
            is_summary = chunk.get("chunk_level") in ["table_summary", "chart_analysis"]
            
            if is_text or is_summary:
                # Limit graph extraction to meaningful content
                graph_tasks.append(extractor.extract_triplets(chunk["content"]))
        
        total_triplets = 0 # Initialize here to ensure it's always defined
        if graph_tasks:
            logger.info("Extracting Knowledge Graph triplets", count=len(graph_tasks))
            
            # Batch task execution to avoid overloading LLM/rate limits
            graph_batch_size = 10
            for i in range(0, len(graph_tasks), graph_batch_size):
                batch_tasks = graph_tasks[i:i + graph_batch_size]
                triplets_list = await asyncio.gather(*batch_tasks)
                
                for triplets in triplets_list:
                    for t in triplets:
                        graph_service.add_triplet(
                            head=t["subject"],
                            relation=t["relation"],
                            tail=t["object"],
                            document_id=document_id,
                            metadata={"source": filename}
                        )
                        total_triplets += 1
                
                if (i // graph_batch_size) % 5 == 0:
                    logger.info("Graph extraction progress", current=i, total=len(graph_tasks))
            
            logger.info("Knowledge Graph updated", triplets=total_triplets)

        # Step 6: Vector Embedding + Upsert
        batch_size = 16
        total_vectors = 0

        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i:i + batch_size]
            texts = [c["content"] for c in batch]

            embeddings = await self.embedding_service.embed_texts(
                texts, input_type="passage"
            )

            payloads = []
            for chunk in batch:
                payload = {
                    "document_id": chunk["document_id"],
                    "source": chunk["source"],
                    "content": chunk["content"],
                    "page": chunk["page"],
                    "content_type": chunk["content_type"],
                    "chunk_level": chunk.get("chunk_level", "paragraph"),
                    "section_hierarchy": chunk.get("section_hierarchy", []),
                    "total_pages": routed_content["processing_stats"].get("total_pages", 0),
                    "metadata": chunk.get("metadata", {}),
                }
                # Include asset path for multimodal retrieval
                if chunk.get("asset_path"):
                    payload["asset_path"] = chunk["asset_path"]
                payloads.append(payload)

            await self.vector_store.upsert(embeddings, payloads)
            total_vectors += len(batch)

        logger.info("Document fully indexed", vectors=total_vectors)

        return {
            "status": "success",
            "document_id": document_id,
            "chunks_count": total_vectors,
            "processing_stats": routed_content.get("processing_stats", {}),
            "graph_triplets": total_triplets if 'total_triplets' in locals() else 0
        }

    def _create_hierarchical_chunks(
        self,
        routed_content: Dict[str, Any],
        doc_id: str,
        filename: str,
        metadata: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Hierarchical Chunking from routed content.

        Transforms:
        - Text sections → Paragraph chunks
        - Canonical tables → Table summary + markdown chunks
        - Chart analyses → Chart analysis chunks
        """
        chunks = []

        # ── 1. Text Chunks (Paragraphs) ──
        for section in routed_content.get("text_sections", []):
            raw_text = section.get("content", "")
            page_num = section.get("page", 1)
            section_title = section.get("title", "")

            if not raw_text:
                continue

            paras = self.chunker._split_into_paragraphs(raw_text)
            for p in paras:
                if len(p.split()) > 20:
                    chunks.append({
                        "content": p,
                        "document_id": doc_id,
                        "source": filename,
                        "page": page_num,
                        "content_type": "text",
                        "chunk_level": "paragraph",
                        "section_hierarchy": [section_title] if section_title else [],
                        "metadata": metadata,
                    })

        # ── 2. Table Chunks (Canonicalized) ──
        for canon_table in routed_content.get("canonical_tables", []):
            page_num = canon_table.page
            table_id = canon_table.table_id

            # Summary chunk (for semantic search)
            summary = canon_table.summary or f"Table on page {page_num}"
            summary_content = f"[TABLE: {table_id}] {summary}"

            if canon_table.metrics_detected:
                summary_content += f"\nMetrics: {', '.join(canon_table.metrics_detected)}"
            if canon_table.time_periods:
                summary_content += f"\nPeriods: {', '.join(canon_table.time_periods)}"

            chunks.append({
                "content": summary_content,
                "document_id": doc_id,
                "source": filename,
                "page": page_num,
                "content_type": "table",
                "chunk_level": "table_summary",
                "asset_path": f"{doc_id}/tables/{table_id}.json",
                "metadata": {**metadata, "table_id": table_id},
            })

            # Detailed markdown chunk (for numerical retrieval)
            markdown = canon_table.to_markdown() if hasattr(canon_table, 'to_markdown') else ""
            if markdown and len(markdown) > 50:
                md_content = f"[TABLE DATA: {table_id}, Page {page_num}]\n{markdown}"
                chunks.append({
                    "content": md_content,
                    "document_id": doc_id,
                    "source": filename,
                    "page": page_num,
                    "content_type": "table",
                    "chunk_level": "table_data",
                    "asset_path": f"{doc_id}/tables/{table_id}.json",
                    "metadata": {**metadata, "table_id": table_id},
                })

        # ── 3. Chart Chunks (Analyzed) ──
        for chart_analysis in routed_content.get("chart_analyses", []):
            page_num = chart_analysis.page
            chart_id = chart_analysis.chart_id

            analysis_text = chart_analysis.semantic_summary or f"Chart on page {page_num}"
            content = f"[CHART: {chart_id}, Type: {chart_analysis.chart_type}]\n{analysis_text}"

            if hasattr(chart_analysis, 'insights') and chart_analysis.insights:
                content += "\nInsights:\n" + "\n".join(
                    f"- {ins}" for ins in chart_analysis.insights[:5]
                )

            chunks.append({
                "content": content,
                "document_id": doc_id,
                "source": filename,
                "page": page_num,
                "content_type": "chart",
                "chunk_level": "chart_analysis",
                "asset_path": f"{doc_id}/charts/{chart_id}.json",
                "metadata": {**metadata, "chart_id": chart_id},
            })

        return chunks

    async def delete_document(self, document_id: str) -> bool:
        """Purge document from all storage tiers."""
        await self.vector_store.delete_by_filter({
            "must": [{"key": "document_id", "match": {"value": document_id}}]
        })
        self.object_storage.delete_object(settings.minio_bucket_documents, f"{document_id}/")
        return True



