# 🚀 RAG-POC Enterprise Upgrade Plan

> **Upgrading to NVIDIA Enterprise RAG Pipeline Architecture**

## ✅ Implementation Status (Updated: 2026-02-09)

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Model Upgrades | ✅ **COMPLETED** |
| 2 | MinIO Object Storage | ✅ **COMPLETED** |
| 3 | Multimodal Parsing Service | ✅ **COMPLETED** |
| 4 | Enhanced Context Assembly | ✅ **COMPLETED** |
| 5 | Guardrails Service | ✅ **COMPLETED** |
| 6 | Observability & Evaluation | ✅ **COMPLETED** |

### NVIDIA API Models

| Component | Current Implementation | Target Implementation | Status |
|-----------|----------------------|----------------------|--------|
| **LLM** | `meta/llama-3.1-70b-instruct` | `llama-3_3-nemotron-super-49b-v1_5` | 🔄 UPGRADE |
| **Embedding** | `nvidia/nv-embedqa-e5-v5` (1024 dim) | `llama-3_2-nv-embedqa-1b-v2` | 🔄 UPGRADE |
| **Reranker** | `nvidia/nv-rerankqa-mistral-4b-v3` | `llama-3_2-nv-rerankqa-1b-v2` | 🔄 UPGRADE |
| **Page Elements** | ❌ Not implemented | `nemoretriever-page-elements-v2` | ⭐ NEW |
| **Table Extraction** | ❌ Not implemented | `nemoretriever-table-structure-v1` | ⭐ NEW |
| **Graphic Extraction** | ❌ Not implemented | `nemoretriever-graphic-elements-v1` | ⭐ NEW |
| **OCR** | ❌ Not implemented | `paddleocr` | ⭐ NEW |

### Data Infrastructure

| Component | Current Implementation | Target Implementation | Status |
|-----------|----------------------|----------------------|--------|
| **Vector DB** | Qdrant ✅ | Qdrant (keep) | ✅ DONE |
| **Metadata DB** | PostgreSQL ✅ | PostgreSQL (keep) | ✅ DONE |
| **Cache** | Redis ✅ | Redis (keep) | ✅ DONE |
| **Object Storage** | Local filesystem | MinIO (S3-compatible) | ⭐ NEW |

### Pipeline Features

| Feature | Current Implementation | Target Implementation | Status |
|---------|----------------------|----------------------|--------|
| **Semantic Search** | ✅ Implemented | ✅ Keep | ✅ DONE |
| **Hybrid Search** | ✅ Implemented | ✅ Keep | ✅ DONE |
| **Reranking** | ✅ Implemented | ✅ Keep | ✅ DONE |
| **Streaming Response** | ✅ SSE Implemented | ✅ Keep | ✅ DONE |
| **Query Rewriting** | ✅ Implemented | ✅ Keep | ✅ DONE |
| **Financial Query Handling** | ✅ Implemented | ✅ Keep | ✅ DONE |
| **Page-based Retrieval** | ✅ Implemented | ✅ Keep | ✅ DONE |
| **Multimodal Parsing** | ❌ Not implemented | nemoretriever APIs | ⭐ NEW |
| **Table Extraction** | ❌ Not implemented | API-based extraction | ⭐ NEW |
| **Chart/Image Analysis** | ❌ Not implemented | Graphic elements API | ⭐ NEW |
| **Governance/Safety** | ❌ Not implemented | NemoGuard APIs | ⭐ NEW |
| **Observability** | Basic logging | OpenTelemetry + RAGAS | 🔄 UPGRADE |

---

## 🎯 Implementation Phases

### Phase 1: Model Upgrades (Priority: HIGH)
**Estimated time: 1-2 days**

Update NVIDIA API model configurations to use latest models.

#### 1.1 Update `.env` and `config.py`

```env
# Updated NVIDIA Models
NVIDIA_LLM_MODEL=nvidia/llama-3.3-nemotron-super-49b-v1
NVIDIA_EMBED_MODEL=nvidia/llama-3.2-nv-embedqa-1b-v2
NVIDIA_RERANK_MODEL=nvidia/llama-3.2-nv-rerankqa-1b-v2
```

**Note**: Verify model availability in NVIDIA NIM catalog before updating.

#### 1.2 Update Embedding Dimension
- New embedding model may have different vector dimensions
- Update `QDRANT_VECTOR_SIZE` accordingly
- **Re-ingest all documents** after dimension change

---

### Phase 2: MinIO Object Storage (Priority: MEDIUM)
**Estimated time: 1-2 days**

Add S3-compatible object storage for document management.

#### 2.1 Add MinIO to docker-compose.yml

```yaml
minio:
  image: minio/minio:latest
  container_name: rag-minio
  ports:
    - "9000:9000"
    - "9001:9001"
  environment:
    - MINIO_ROOT_USER=${MINIO_ROOT_USER:-ragadmin}
    - MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD:-ragpass123}
  volumes:
    - minio_data:/data
  command: server /data --console-address ":9001"
  networks:
    - rag-network
  healthcheck:
    test: ["CMD", "mc", "ready", "local"]
    interval: 30s
    timeout: 20s
    retries: 3
```

#### 2.2 Create Object Storage Service

```python
# backend/services/object_storage_service.py
from minio import Minio
from core.config import settings

class ObjectStorageService:
    def __init__(self):
        self.client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure
        )
    
    async def upload_document(self, file, document_id):
        """Upload original document to MinIO"""
        
    async def upload_parsed_asset(self, asset, document_id, asset_type):
        """Upload parsed images, tables, etc."""
        
    async def get_document(self, document_id):
        """Retrieve original document"""
```

#### 2.3 Environment Variables

```env
# MinIO Configuration
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=ragadmin
MINIO_SECRET_KEY=ragpass123
MINIO_SECURE=false
MINIO_BUCKET_DOCUMENTS=documents
MINIO_BUCKET_ASSETS=parsed-assets
```

---

### Phase 3: Multimodal Document Parsing (Priority: HIGH)
**Estimated time: 3-5 days**

Implement NVIDIA NIM multimodal parsing APIs for enhanced document understanding.

#### 3.1 Create Multimodal Parser Service

```python
# backend/services/multimodal_parser_service.py

class MultimodalParserService:
    """NVIDIA NIM multimodal document parsing service."""
    
    async def extract_page_elements(self, pdf_bytes, page_num):
        """
        Use nemoretriever-page-elements-v2 API
        Returns: text blocks, layout info, bounding boxes
        """
        
    async def extract_tables(self, pdf_bytes, page_num):
        """
        Use nemoretriever-table-structure-v1 API
        Returns: structured table data (rows, columns, cells)
        """
        
    async def extract_graphics(self, pdf_bytes, page_num):
        """
        Use nemoretriever-graphic-elements-v1 API
        Returns: chart/image descriptions, captions
        """
        
    async def ocr_scan(self, image_bytes):
        """
        Use paddleocr API
        Returns: extracted text from scanned images
        """
```

#### 3.2 Update Ingestion Pipeline

```python
# Existing: backend/ingestion/embedding_pipeline.py
# Add multimodal support

class EnhancedEmbeddingPipeline:
    def __init__(self):
        self.multimodal_parser = MultimodalParserService()
        self.embedding_service = EmbeddingService()
        self.object_storage = ObjectStorageService()
    
    async def process_document(self, document_id, file_bytes):
        # 1. Store original in MinIO
        await self.object_storage.upload_document(file_bytes, document_id)
        
        # 2. Extract page elements
        page_elements = await self.multimodal_parser.extract_page_elements(file_bytes)
        
        # 3. Extract tables
        tables = await self.multimodal_parser.extract_tables(file_bytes)
        
        # 4. Extract graphics/charts
        graphics = await self.multimodal_parser.extract_graphics(file_bytes)
        
        # 5. Store parsed assets
        await self.object_storage.upload_parsed_asset(tables, document_id, "tables")
        await self.object_storage.upload_parsed_asset(graphics, document_id, "graphics")
        
        # 6. Generate embeddings for all content types
        # 7. Store in Qdrant with rich metadata
```

#### 3.3 Environment Variables

```env
# Multimodal Parsing APIs
NVIDIA_PAGE_ELEMENTS_MODEL=nvidia/nemoretriever-page-elements-v2
NVIDIA_TABLE_MODEL=nvidia/nemoretriever-table-structure-v1
NVIDIA_GRAPHIC_MODEL=nvidia/nemoretriever-graphic-elements-v1
NVIDIA_OCR_MODEL=paddleocr
```

---

### Phase 4: Enhanced Context Assembly (Priority: MEDIUM)
**Estimated time: 1-2 days**

Improve how context is assembled for LLM generation.

#### 4.1 Update RAG Pipeline

```python
# backend/workflow/rag_pipeline.py - Enhanced context assembly

async def assemble_context(self, retrieved_docs, query_analysis):
    """
    Merge multiple content types:
    - Text chunks
    - Table summaries
    - Image/chart captions
    - Conversation memory (if applicable)
    """
    
    context_sections = []
    
    # Group by content type
    text_docs = [d for d in retrieved_docs if d['type'] == 'text']
    table_docs = [d for d in retrieved_docs if d['type'] == 'table']
    graphic_docs = [d for d in retrieved_docs if d['type'] == 'graphic']
    
    if text_docs:
        context_sections.append("## Text Content\n" + format_text_context(text_docs))
    
    if table_docs:
        context_sections.append("## Table Data\n" + format_table_context(table_docs))
    
    if graphic_docs:
        context_sections.append("## Charts & Graphics\n" + format_graphic_context(graphic_docs))
    
    return "\n\n---\n\n".join(context_sections)
```

---

### Phase 5: Governance & Safety (Priority: MEDIUM)
**Estimated time: 2-3 days**

Add content moderation and safety guardrails.

#### 5.1 Create Guardrails Service

```python
# backend/services/guardrails_service.py

class GuardrailsService:
    """NVIDIA NemoGuard content moderation service."""
    
    async def check_input(self, user_query):
        """
        Pre-generation safety check:
        - Prompt injection detection
        - Topic restriction enforcement
        - PII detection
        """
        
    async def check_output(self, llm_response):
        """
        Post-generation safety check:
        - Content moderation
        - Hallucination detection
        - Factuality verification
        """
        
    async def validate_access(self, user, document_ids):
        """
        Role-based access control:
        - Document-level permissions
        - User role verification
        """
```

#### 5.2 Integrate into Pipeline

```python
# In rag_pipeline.py

async def execute_with_guardrails(self, query, user):
    # Pre-check
    input_safe = await self.guardrails.check_input(query)
    if not input_safe:
        return {"error": "Query blocked by safety filter"}
    
    # Execute RAG
    response = await self.execute(query)
    
    # Post-check
    output_safe = await self.guardrails.check_output(response)
    if not output_safe:
        return {"error": "Response blocked by safety filter"}
    
    return response
```

---

### Phase 6: Observability & Evaluation (Priority: LOW)
**Estimated time: 2-3 days**

Add comprehensive monitoring, tracing, and quality evaluation.

#### 6.1 OpenTelemetry Integration

```python
# backend/core/telemetry.py

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

def setup_telemetry(app):
    """Configure OpenTelemetry for distributed tracing."""
    provider = TracerProvider()
    processor = BatchSpanProcessor(OTLPSpanExporter())
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    
    FastAPIInstrumentor.instrument_app(app)
```

#### 6.2 RAGAS Evaluation Framework

```python
# backend/services/evaluation_service.py

from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall
)

class EvaluationService:
    """RAG quality evaluation using RAGAS."""
    
    async def evaluate_response(self, query, response, context, ground_truth=None):
        """
        Evaluate RAG response quality:
        - Faithfulness: Is the answer grounded in context?
        - Relevancy: Is the answer relevant to the question?
        - Context Precision: Is the context relevant?
        - Context Recall: Does context cover the answer?
        """
        
    async def log_evaluation_metrics(self, metrics):
        """Log to monitoring system for dashboards."""
```

#### 6.3 Prometheus Metrics

```python
# backend/core/metrics.py

from prometheus_client import Counter, Histogram, Gauge

# RAG Pipeline Metrics
query_latency = Histogram(
    'rag_query_latency_seconds',
    'RAG query processing time',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

retrieval_count = Counter(
    'rag_retrieval_total',
    'Total retrieval requests',
    ['status']
)

context_chunks = Histogram(
    'rag_context_chunks',
    'Number of context chunks used',
    buckets=[1, 3, 5, 10, 15, 20]
)

rerank_score = Gauge(
    'rag_rerank_top_score',
    'Top reranking score'
)
```

---

## 📁 New File Structure

```
backend/
├── services/
│   ├── nvidia_llm_service.py       # Existing ✅
│   ├── embedding_service.py        # Existing ✅
│   ├── vector_store_service.py     # Existing ✅
│   ├── retrieval_service.py        # Existing ✅
│   ├── reranker_service.py         # Existing ✅
│   ├── object_storage_service.py   # NEW ⭐
│   ├── multimodal_parser_service.py # NEW ⭐
│   ├── guardrails_service.py       # NEW ⭐
│   └── evaluation_service.py       # NEW ⭐
├── core/
│   ├── config.py                   # Update with new settings
│   ├── logger.py                   # Existing ✅
│   ├── telemetry.py               # NEW ⭐
│   └── metrics.py                 # NEW ⭐
└── ingestion/
    ├── chunking_strategy.py        # Existing ✅
    ├── embedding_pipeline.py       # Update for multimodal
    └── multimodal_pipeline.py      # NEW ⭐
```

---

## 🔧 Configuration Updates Required

### Updated .env

```env
# ============================================
# NVIDIA NIM Configuration (UPDATED)
# ============================================
NVIDIA_API_KEY=your-api-key
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1

# Core Models (UPDATED)
NVIDIA_LLM_MODEL=nvidia/llama-3.3-nemotron-super-49b-v1
NVIDIA_EMBED_MODEL=nvidia/llama-3.2-nv-embedqa-1b-v2
NVIDIA_RERANK_MODEL=nvidia/llama-3.2-nv-rerankqa-1b-v2

# Multimodal Parsing Models (NEW)
NVIDIA_PAGE_ELEMENTS_MODEL=nvidia/nemoretriever-page-elements-v2
NVIDIA_TABLE_MODEL=nvidia/nemoretriever-table-structure-v1
NVIDIA_GRAPHIC_MODEL=nvidia/nemoretriever-graphic-elements-v1
NVIDIA_OCR_MODEL=paddleocr

# Guardrails (NEW)
NVIDIA_GUARDRAILS_ENABLED=true
NVIDIA_INPUT_GUARDRAILS=true
NVIDIA_OUTPUT_GUARDRAILS=true

# ============================================
# MinIO Object Storage (NEW)
# ============================================
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=ragadmin
MINIO_SECRET_KEY=ragpass123
MINIO_SECURE=false
MINIO_BUCKET_DOCUMENTS=documents
MINIO_BUCKET_ASSETS=parsed-assets

# ============================================
# Observability (NEW)
# ============================================
OTLP_ENDPOINT=http://jaeger:4317
ENABLE_TRACING=true
ENABLE_METRICS=true
METRICS_PORT=9090
RAGAS_EVALUATION_ENABLED=true
```

---

## ⏱️ Implementation Timeline

| Phase | Description | Time Estimate | Priority |
|-------|-------------|---------------|----------|
| 1 | Model Upgrades | 1-2 days | HIGH |
| 2 | MinIO Object Storage | 1-2 days | MEDIUM |
| 3 | Multimodal Parsing | 3-5 days | HIGH |
| 4 | Enhanced Context Assembly | 1-2 days | MEDIUM |
| 5 | Governance & Safety | 2-3 days | MEDIUM |
| 6 | Observability & Evaluation | 2-3 days | LOW |

**Total Estimated Time: 10-17 days**

---

## ⚠️ Migration Considerations

### Breaking Changes
1. **Embedding Model Change**: Requires re-ingestion of all documents
2. **Vector Dimension Change**: May require Qdrant collection recreation
3. **API Endpoint Changes**: New models may have different API interfaces

### Recommended Migration Steps
1. **Test in staging environment first**
2. **Backup existing Qdrant data**
3. **Update models incrementally** (LLM first, then embeddings)
4. **Re-ingest a subset of documents** to verify quality
5. **Full re-ingestion** after validation

---

## 📝 Next Steps

1. **Verify Model Availability**: Check NVIDIA NIM catalog for model names
2. **Start with Phase 1**: Update model configurations
3. **Test Model Quality**: Compare response quality before/after
4. **Plan Document Re-ingestion**: Schedule downtime if needed
5. **Proceed with Infrastructure Phases**: MinIO, multimodal parsing

---

*Generated: 2026-02-09*
*For: RAG-POC Enterprise Upgrade*
