# 🚀 NVIDIA NIM Powered RAG + Agentic Backend System - Implementation Plan

## 📋 Overview

This document outlines the implementation plan for a production-ready, fully Dockerized backend system supporting Retrieval Augmented Generation (RAG) and Agentic AI chat workflows using NVIDIA NIM APIs.

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Docker Network                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │   FastAPI   │    │   Qdrant    │    │  PostgreSQL │    │    Redis    │  │
│  │   Backend   │◄──►│  Vector DB  │    │   Database  │    │    Cache    │  │
│  │   (API)     │    │             │    │             │    │             │  │
│  └──────┬──────┘    └─────────────┘    └──────┬──────┘    └──────┬──────┘  │
│         │                                      │                  │         │
│         │           ┌─────────────┐           │                  │         │
│         └──────────►│  Ingestion  │◄──────────┴──────────────────┘         │
│                     │   Worker    │                                         │
│                     └─────────────┘                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
                        ┌─────────────────────────┐
                        │    NVIDIA NIM APIs      │
                        │  - LLM Inference        │
                        │  - Embeddings (nv-embed)│
                        │  - Reranking            │
                        └─────────────────────────┘
```

---

## 📁 Project Structure

```
RAG-POC/
├── backend/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── chat_routes.py          # Chat endpoint with SSE streaming
│   │   ├── ingestion_routes.py     # Document upload and ingestion
│   │   ├── auth_routes.py          # JWT authentication
│   │   └── health_routes.py        # Health checks & metrics
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py               # Pydantic Settings configuration
│   │   ├── security.py             # JWT & authentication utilities
│   │   ├── logger.py               # Structured JSON logging
│   │   └── dependency_injection.py # FastAPI dependencies
│   ├── workflow/
│   │   ├── __init__.py
│   │   ├── orchestrator.py         # Main workflow orchestrator
│   │   ├── query_router.py         # Query classification engine
│   │   ├── rag_pipeline.py         # RAG workflow steps
│   │   ├── tool_pipeline.py        # Tool execution (placeholder)
│   │   └── response_synthesizer.py # Response generation
│   ├── services/
│   │   ├── __init__.py
│   │   ├── nvidia_llm_service.py   # NVIDIA LLM API integration
│   │   ├── embedding_service.py    # NVIDIA embedding service
│   │   ├── reranker_service.py     # Reranking service
│   │   ├── vector_store_service.py # Qdrant operations
│   │   ├── retrieval_service.py    # Vector retrieval logic
│   │   ├── memory_service.py       # Chat history management
│   │   └── document_parser_service.py # Document parsing
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── ingest_worker.py        # Async ingestion worker
│   │   ├── chunking_strategy.py    # Semantic chunking
│   │   └── embedding_pipeline.py   # Document embedding pipeline
│   ├── db/
│   │   ├── __init__.py
│   │   ├── postgres_models.py      # SQLAlchemy models
│   │   └── session_manager.py      # Database session management
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── chat_schema.py          # Chat request/response schemas
│   │   └── ingestion_schema.py     # Ingestion schemas
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── streaming.py            # SSE streaming utilities
│   │   └── token_counter.py        # Token counting utilities
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── unit/
│   │   │   ├── test_nvidia_llm_service.py
│   │   │   ├── test_embedding_service.py
│   │   │   ├── test_query_router.py
│   │   │   └── test_rag_pipeline.py
│   │   ├── integration/
│   │   │   ├── test_chat_workflow.py
│   │   │   └── test_ingestion_workflow.py
│   │   └── conftest.py             # Test fixtures and mocks
│   ├── main.py                     # FastAPI application entry
│   └── requirements.txt            # Python dependencies
├── docker/
│   ├── api/
│   │   └── Dockerfile              # FastAPI container
│   ├── ingestion/
│   │   └── Dockerfile              # Ingestion worker container
│   └── nginx/
│       └── nginx.conf              # Optional reverse proxy
├── scripts/
│   ├── init_db.py                  # Database initialization
│   └── seed_data.py                # Optional seed data
├── docker-compose.yml              # Main compose file
├── docker-compose.override.yml     # Development overrides
├── .env.example                    # Environment template
├── Makefile                        # CLI shortcuts
└── README.md                       # Documentation
```

---

## 📅 Implementation Phases

### Phase 1: Foundation & Infrastructure (Day 1) ✅ COMPLETED

#### 1.1 Project Setup
- [x] Create project directory structure
- [x] Initialize Python virtual environment
- [x] Create `requirements.txt` with all dependencies
- [x] Create `.env.example` with all configuration variables

#### 1.2 Docker Infrastructure
- [x] Create `docker-compose.yml` with all services:
  - FastAPI API service
  - Qdrant vector database
  - PostgreSQL database
  - Redis cache
  - Ingestion worker
- [ ] Create multi-stage Dockerfiles:
  - `docker/api/Dockerfile`
  - `docker/ingestion/Dockerfile`
- [ ] Configure Docker networks and volumes
- [ ] Add health checks for all services

#### 1.3 Core Configuration
- [ ] Implement `core/config.py` with Pydantic Settings
- [ ] Implement `core/logger.py` with structured JSON logging
- [ ] Create request tracing middleware

**Deliverables:**
- Working Docker Compose stack
- Configuration management system
- Structured logging infrastructure

---

### Phase 2: Database & Persistence Layer (Day 1-2)

#### 2.1 PostgreSQL Setup
- [ ] Create `db/postgres_models.py` with SQLAlchemy models:
  - User model
  - ChatSession model
  - ChatMessage model
  - Document model
  - DocumentChunk model
- [ ] Implement `db/session_manager.py` for async sessions
- [ ] Create Alembic migrations setup

#### 2.2 Redis Integration
- [ ] Implement Redis connection manager
- [ ] Create rate limiting utilities
- [ ] Implement caching decorators

#### 2.3 Vector Store Setup
- [ ] Implement `services/vector_store_service.py`:
  - Collection management
  - Vector upsert operations
  - Similarity search
  - Filtering capabilities

**Deliverables:**
- Database models and migrations
- Redis caching layer
- Qdrant vector store service

---

### Phase 3: NVIDIA NIM Integration (Day 2)

#### 3.1 LLM Service
- [ ] Implement `services/nvidia_llm_service.py`:
  - Async API client
  - Streaming response support
  - Retry logic with exponential backoff
  - Timeout management
  - Error handling and fallbacks

#### 3.2 Embedding Service
- [ ] Implement `services/embedding_service.py`:
  - NVIDIA nv-embed-v1 integration
  - Batch embedding support
  - Embedding caching layer
  - Async processing

#### 3.3 Reranker Service
- [ ] Implement `services/reranker_service.py`:
  - NVIDIA reranker API integration
  - Score-based reordering
  - Configurable top-k selection

**Deliverables:**
- NVIDIA LLM integration with streaming
- Embedding service with caching
- Reranker service (placeholder ready)

---

### Phase 4: RAG Workflow Implementation (Day 2-3)

#### 4.1 Query Router
- [ ] Implement `workflow/query_router.py`:
  - Query classification using lightweight model
  - Route types: DIRECT_LLM, RAG_PIPELINE, TOOL_PIPELINE
  - Confidence scoring
  - Fallback handling

#### 4.2 RAG Pipeline
- [ ] Implement `workflow/rag_pipeline.py`:
  - Query rewriting step
  - Query embedding generation
  - Vector similarity retrieval
  - Reranking step
  - Context aggregation
  - Prompt synthesis

#### 4.3 Response Synthesizer
- [ ] Implement `workflow/response_synthesizer.py`:
  - Context-aware prompt building
  - System prompt management
  - Token budget management

#### 4.4 Workflow Orchestrator
- [ ] Implement `workflow/orchestrator.py`:
  - Main workflow coordination
  - Pipeline selection and execution
  - Error handling and fallbacks
  - Timing metrics collection

**Deliverables:**
- Complete RAG pipeline
- Query routing engine
- Workflow orchestrator

---

### Phase 5: Document Ingestion Pipeline (Day 3)

#### 5.1 Document Parser
- [ ] Implement `services/document_parser_service.py`:
  - PDF parsing (using pypdf or pdfplumber)
  - DOCX parsing (using python-docx)
  - TXT file handling
  - Pluggable parser interface

#### 5.2 Chunking Strategy
- [ ] Implement `ingestion/chunking_strategy.py`:
  - Semantic chunking algorithm
  - Configurable chunk sizes
  - Overlap handling
  - Metadata preservation

#### 5.3 Embedding Pipeline
- [ ] Implement `ingestion/embedding_pipeline.py`:
  - Batch document processing
  - Parallel embedding generation
  - Vector store insertion
  - Metadata storage

#### 5.4 Ingestion Worker
- [ ] Implement `ingestion/ingest_worker.py`:
  - Async job processing
  - Queue management
  - Progress tracking
  - Error handling

**Deliverables:**
- Document parsing for PDF, DOCX, TXT
- Semantic chunking
- Async ingestion worker

---

### Phase 6: API Layer & Authentication (Day 3-4)

#### 6.1 Security Implementation
- [ ] Implement `core/security.py`:
  - JWT token generation/validation
  - Password hashing
  - API key management
- [ ] Implement rate limiting middleware

#### 6.2 Chat Routes
- [ ] Implement `api/chat_routes.py`:
  - POST /chat endpoint
  - SSE streaming support
  - Chat history integration
  - Session management

#### 6.3 Ingestion Routes
- [x] Implement `api/ingestion_routes.py`:
  - [x] POST /ingest endpoint (file upload)
  - [x] GET /documents endpoint
  - [x] Document status tracking (PostgreSQL + Redis)
  - [x] GET /ingest/files/{document_id} (File download)
  - [x] UI Improvements:
    - [x] Implemented "View Source" functionality in `SourcePanel`
    - [x] Added `document_id` to streaming sources
    - [x] Fixed document status polling

#### 6.4 Auth Routes
- [ ] Implement `api/auth_routes.py`:
  - POST /auth/login endpoint
  - Token refresh support

#### 6.5 Health Routes
- [ ] Implement `api/health_routes.py`:
  - GET /health endpoint
  - Service dependency checks
  - Prometheus metrics placeholder

**Deliverables:**
- Complete API layer
- JWT authentication
- Rate limiting

---

### Phase 7: Streaming & Memory (Day 4)

#### 7.1 Streaming Utilities
- [ ] Implement `utils/streaming.py`:
  - SSE event formatting
  - Token-level streaming
  - Graceful cancellation
  - Connection management

#### 7.2 Memory Service
- [ ] Implement `services/memory_service.py`:
  - Chat history persistence
  - Session tracking
  - Last N messages retrieval
  - Summarization placeholder

#### 7.3 Token Counter
- [ ] Implement `utils/token_counter.py`:
  - Token counting utilities
  - Context window management
  - Usage monitoring

**Deliverables:**
- SSE streaming implementation
- Chat memory persistence
- Token management

---

### Phase 8: Testing & Documentation (Day 4-5)

#### 8.1 Unit Tests
- [ ] Create unit tests for:
  - NVIDIA LLM service (with mocks)
  - Embedding service
  - Query router
  - RAG pipeline
  - Chunking strategy

#### 8.2 Integration Tests
- [ ] Create integration tests for:
  - Full chat workflow
  - Document ingestion workflow
  - Authentication flow

#### 8.3 Documentation
- [ ] Create comprehensive README.md
- [ ] Document API endpoints
- [ ] Create deployment guide
- [ ] Document environment variables

**Deliverables:**
- Complete test suite
- Documentation

---

### Phase 9: Polish & Production Readiness (Day 5)

#### 9.1 Error Handling
- [ ] Implement global error handlers
- [ ] Create error response schemas
- [ ] Add retry logic everywhere

#### 9.2 Performance Optimization
- [ ] Add connection pooling
- [ ] Optimize database queries
- [ ] Configure batch sizes

#### 9.3 Observability
- [ ] Add timing metrics
- [ ] Configure log aggregation
- [ ] Add Prometheus metrics placeholders

**Deliverables:**
- Production-ready system
- Complete observability

---

## 🔧 Technology Specifications

### Python Dependencies

```
# Core Framework
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
gunicorn>=21.2.0
python-multipart>=0.0.9

# NVIDIA & AI
llama-index>=0.10.0
openai>=1.12.0  # For NVIDIA NIM OpenAI-compatible API
httpx>=0.26.0

# Database
sqlalchemy[asyncio]>=2.0.25
asyncpg>=0.29.0
alembic>=1.13.0
psycopg2-binary>=2.9.9

# Vector Store
qdrant-client>=1.7.0

# Redis
redis>=5.0.1
aioredis>=2.0.1

# Document Processing
pypdf>=4.0.0
python-docx>=1.1.0
tiktoken>=0.5.2

# Authentication
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4

# Utilities
pydantic>=2.5.0
pydantic-settings>=2.1.0
python-dotenv>=1.0.0

# Testing
pytest>=8.0.0
pytest-asyncio>=0.23.0
pytest-cov>=4.1.0
httpx>=0.26.0  # For async test client

# Logging
structlog>=24.1.0
```

### Environment Variables

```env
# Application
APP_NAME=rag-backend
APP_ENV=development
DEBUG=true
LOG_LEVEL=INFO

# API Server
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4

# NVIDIA NIM Configuration
NVIDIA_API_KEY=nvapi-xxx
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_LLM_MODEL=meta/llama-3.1-70b-instruct
NVIDIA_EMBED_MODEL=nvidia/nv-embed-v1
NVIDIA_RERANK_MODEL=nvidia/nv-rerankqa-mistral-4b-v3

# PostgreSQL
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=ragdb
POSTGRES_USER=raguser
POSTGRES_PASSWORD=ragpass

# Qdrant
QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_COLLECTION=documents

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# Security
JWT_SECRET_KEY=your-secret-key
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=60

# RAG Configuration
CHUNK_SIZE=512
CHUNK_OVERLAP=50
TOP_K_RETRIEVAL=5
RERANK_TOP_K=3
```

---

## 🐳 Docker Services Configuration

### Service Dependencies

```yaml
services:
  api:
    depends_on:
      - postgres
      - qdrant
      - redis
    
  ingestion-worker:
    depends_on:
      - postgres
      - qdrant
      - redis

  postgres:
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U raguser -d ragdb"]
      
  qdrant:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/health"]
      
  redis:
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
```

### Volume Persistence

```yaml
volumes:
  postgres_data:
  qdrant_data:
  redis_data:
  upload_data:
```

---

## 🔄 Workflow Execution Flow

### Chat Request Flow

```
1. User sends POST /chat with query + session_id
2. JWT authentication middleware validates token
3. Rate limiter checks request quota
4. Orchestrator receives request
5. Query Router classifies query → [DIRECT_LLM | RAG_PIPELINE | TOOL_PIPELINE]
6. If RAG_PIPELINE:
   a. Query Rewriter optimizes query
   b. Embedding Service generates query embedding
   c. Retrieval Service fetches top-k vectors from Qdrant
   d. Reranker reorders results
   e. Context Aggregator combines chunks
   f. Response Synthesizer builds prompt
   g. NVIDIA LLM generates streaming response
7. Response streamed via SSE
8. Chat history persisted to PostgreSQL
9. Metrics logged
```

### Ingestion Flow

```
1. User sends POST /ingest with file
2. File validated and stored temporarily
3. Job queued for ingestion worker
4. Worker:
   a. Parses document (PDF/DOCX/TXT)
   b. Chunks document semantically
   c. Generates embeddings via NVIDIA API
   d. Stores vectors in Qdrant
   e. Stores metadata in PostgreSQL
5. Status updated to complete
```

---

## ✅ Success Criteria

1. **Single Command Deployment**: `docker compose up -d` starts entire stack
2. **Chat Functionality**: Streaming chat with RAG retrieval works
3. **Document Ingestion**: PDF/DOCX/TXT files can be ingested
4. **Authentication**: JWT auth protects endpoints
5. **Persistence**: Chat history and documents persist across restarts
6. **Observability**: Structured logs with request tracing
7. **Error Handling**: Graceful failures with informative messages
8. **Tests**: Unit and integration tests pass

---

## 🚦 Risk Mitigation

| Risk | Mitigation |
|------|------------|
| NVIDIA API rate limits | Implement exponential backoff and caching |
| Large document processing | Async worker with progress tracking |
| Memory issues with embeddings | Batch processing with configurable sizes |
| Database connection exhaustion | Connection pooling with limits |
| Token limit exceeded | Token counting and context truncation |

---

## 📊 Estimated Timeline

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1: Foundation | 4-6 hours | None |
| Phase 2: Database | 3-4 hours | Phase 1 |
| Phase 3: NVIDIA Integration | 4-5 hours | Phase 1 |
| Phase 4: RAG Workflow | 5-6 hours | Phases 2, 3 |
| Phase 5: Ingestion | 4-5 hours | Phases 2, 3 |
| Phase 6: API Layer | 4-5 hours | Phases 4, 5 |
| Phase 7: Streaming & Memory | 3-4 hours | Phase 6 |
| Phase 8: Testing | 4-5 hours | All phases |
| Phase 9: Polish | 3-4 hours | Phase 8 |

**Total Estimated Time: 35-45 hours**

---

## 🎯 Next Steps

1. **Review and approve this plan**
2. **Begin Phase 1: Foundation & Infrastructure**
3. **Proceed sequentially through phases**
4. **Continuous testing and validation**

---

*Plan created: 2026-02-09*
*Version: 1.0*
