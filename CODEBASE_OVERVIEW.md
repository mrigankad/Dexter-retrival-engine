# Context RAG - Codebase Overview & Quick Reference

**Project Type:** Enterprise-Grade Retrieval Augmented Generation System
**Stack:** FastAPI (Python) + React (TypeScript) + PostgreSQL + Qdrant
**Current Version:** 1.0.0 (Production Ready)
**Date:** February 27, 2026

---

## Quick Navigation Map

```
📁 Context Rag/
├── 📂 backend/                    Python FastAPI Application
│   ├── 📂 api/                   API Route Handlers (6 files)
│   ├── 📂 core/                  Core Infrastructure
│   ├── 📂 db/                    Database Layer (PostgreSQL)
│   ├── 📂 services/              Business Logic (18+ services)
│   ├── 📂 workflow/              Query Processing Pipeline
│   ├── 📂 ingestion/             Document Processing
│   ├── 📂 schemas/               Pydantic Models
│   ├── 📂 tests/                 Test Suite
│   ├── 📂 reports/               Report Generation
│   ├── 📂 workers/               Background Jobs
│   ├── 📂 knowledge/             Entity Extraction
│   ├── 📄 main.py                FastAPI App Entry Point
│   └── 📄 requirements.txt        Python Dependencies
│
├── 📂 frontend/                   React/TypeScript Application
│   ├── 📂 src/
│   │   ├── 📂 pages/             Page Components (3)
│   │   ├── 📂 components/        UI Components (12+)
│   │   ├── 📂 services/          API Client
│   │   ├── 📂 stores/            Zustand State
│   │   ├── 📂 api/               Streaming Client
│   │   ├── 📂 types/             TypeScript Interfaces
│   │   ├── 📄 App.tsx            Router
│   │   └── 📄 main.tsx           Entry Point
│   ├── 📄 vite.config.ts         Build Config
│   ├── 📄 package.json           Dependencies
│   └── 📄 Dockerfile             Container Image
│
├── 📂 docker/                     Container Configurations
├── 📂 scripts/                    Utility Scripts
├── 📄 docker-compose.yml          Multi-container Setup
├── 📄 Makefile                    Build & Dev Commands
├── 📄 .env.example                Environment Template
├── 📄 README.md                   Main Documentation
├── 📄 Architecture.md             Detailed Architecture (73KB)
├── 📄 IMPLEMENTATION_PLAN_V3.md   Implementation Guide
└── 📄 FUTURE_PLAN.md              Strategic Roadmap (this document)
```

---

## Core System Components

### 1. Query Processing Pipeline

**Location:** `backend/workflow/`

```
User Query
    ↓
QueryRouter (route decision)
    ├→ RAG_PIPELINE (document needed)
    │   └→ RAGPipeline (multi-hop retrieval)
    │       ├→ Decompose query
    │       ├→ Execute sub-queries (parallel)
    │       ├→ Compress context
    │       └→ Synthesize answer
    │
    ├→ DIRECT_LLM (general knowledge)
    │   └→ Direct response from LLM
    │
    └→ TOOL_PIPELINE (tool-assisted)
        └→ Execute tools + combine results
```

**Key Files:**
- `orchestrator.py` - Main coordinator
- `rag_pipeline.py` - RAG execution engine
- `query_router.py` - Route decisions
- `multi_hop_executor.py` - Parallel execution
- `synthesis_engine.py` - Answer generation

### 2. Document Ingestion Pipeline

**Location:** `backend/ingestion/`

```
Upload File
    ↓
Document Parser (multiple strategies)
    ├→ DoclingParser (advanced PDF)
    ├→ MarkerFallback (conversion-based)
    └→ ChartAnalyzer (extract charts/tables)
    ↓
Chunking Strategy
    ├→ Hierarchical splitting
    └→ Smart overlap (100 tokens)
    ↓
Embedding Pipeline
    └→ NVIDIA Embeddings (1024-dim)
    ↓
Vector Storage
    └→ Qdrant (vector DB)
    ↓
Database
    └→ PostgreSQL (metadata)
```

**Key Files:**
- `ingest_worker.py` - Background processor
- `embedding_pipeline.py` - Chunk → embeddings
- `docling_parser.py` - Advanced parsing
- `chunking_strategy.py` - Segmentation
- `chart_analyzer.py` - Visual extraction

### 3. Retrieval & Search System

**Location:** `backend/services/`

```
Query
    ↓
Embedding Service
    └→ Text → Vector (1024-dim)
    ↓
Retrieval Service (hybrid search)
    ├→ Vector search (semantic)
    │   └→ Qdrant similarity
    │
    ├→ Keyword search
    │   └→ Boundary matching
    │
    └→ Combine & weight (0.7:0.3)
    ↓
Reranker Service
    └→ Re-rank top results
    ↓
Return Results (with metadata)
```

**Key Files:**
- `embedding_service.py` - Text encoding
- `retrieval_service.py` - Hybrid search
- `reranker_service.py` - Result ranking
- `vector_store_service.py` - Qdrant ops

### 4. API Layer

**Location:** `backend/api/`

| Route | Method | Purpose |
|-------|--------|---------|
| `/health` | GET | Health checks |
| `/auth/login` | POST | JWT authentication |
| `/chat` | POST | Chat interface (SSE) |
| `/ingest` | POST | Document upload |
| `/documents` | GET | List documents |
| `/evaluations` | GET/POST | RAG metrics |
| `/reports` | POST | Generate reports |

**Key Files:**
- `health_routes.py` - Health endpoints
- `auth_routes.py` - Authentication
- `chat_routes.py` - Chat with streaming
- `ingestion_routes.py` - Document upload
- `report_routes.py` - Report generation
- `evaluation_routes.py` - Quality metrics

### 5. Database Schema

**Location:** `backend/db/postgres_models.py`

**Key Tables:**
- `users` - Authentication & sessions
- `chat_sessions` - Conversation containers
- `chat_messages` - Individual messages
- `documents` - Ingestion metadata
- `document_chunks` - Chunks with vector refs

**Relationships:**
```
users (1) ──→ (many) chat_sessions
users (1) ──→ (many) documents
chat_sessions (1) ──→ (many) chat_messages
documents (1) ──→ (many) document_chunks
```

### 6. Frontend Architecture

**Location:** `frontend/src/`

```
Pages (3):
  ├── LoginPage (auth)
  ├── ChatPage (main interface)
  └── DocumentsPage (doc management)

Components (12+):
  ├── ChatInterface (input/output)
  ├── ChatMessage (message display)
  ├── SourcePanel (retrieved docs)
  ├── QualityBadge (answer quality)
  └── ... (more UI components)

State (Zustand):
  ├── authStore (JWT, user)
  ├── chatStore (messages, sessions)
  └── documentStore (files, metadata)

Services:
  └── api.ts (Axios with interceptor)

Streaming:
  ├── chatStream.ts (SSE client)
  └── streamParser.ts (event parsing)
```

---

## Important Files & Locations

### Configuration
- `.env.example` - Template for environment variables
- `backend/core/config.py` - Pydantic settings loader
- `docker-compose.yml` - Service orchestration

### Key Services
- `backend/services/nvidia_llm_service.py` - LLM integration
- `backend/services/evaluation_service.py` - Quality metrics (RAGAS)
- `backend/services/knowledge_graph_service.py` - Neo4j operations
- `backend/workflow/orchestrator.py` - Main coordinator

### Entry Points
- `backend/main.py` - FastAPI app initialization
- `frontend/src/main.tsx` - React app entry
- `frontend/src/App.tsx` - Router setup

### Tests
- `backend/tests/unit/` - Unit tests
- `backend/tests/integration/` - Integration tests

### Docker
- `docker-compose.yml` - Local development setup
- `backend/Dockerfile` - API container
- `frontend/Dockerfile` - Frontend container
- `docker/api/Dockerfile` - Production API image
- `docker/ingestion/Dockerfile` - Worker image

---

## Technology Stack Details

### Backend
- **Framework:** FastAPI 0.109+ (async HTTP)
- **Language:** Python 3.8+
- **Server:** Uvicorn/Gunicorn (ASGI)
- **Database:** PostgreSQL (asyncpg) + SQLAlchemy 2.0
- **Cache:** Redis
- **Vector DB:** Qdrant
- **Object Storage:** MinIO
- **Graph DB:** Neo4j

### AI/ML Services
- **LLM:** Llama 3.3 Nemotron 49B (via NVIDIA NIM)
- **Embeddings:** NVIDIA LLaMA-Embed v2 (1024-dim)
- **Reranking:** NVIDIA LLaMA Reranker v2
- **OCR:** PaddleOCR
- **Document Parsing:** docling, pypdf, python-docx

### Frontend
- **Framework:** React 18.3 + TypeScript 5.5
- **Build:** Vite 5.4
- **State:** Zustand 4.5
- **HTTP:** Axios 1.6 (with interceptors)
- **UI:** Tailwind CSS 4.0, HeadlessUI, Lucide icons
- **Animations:** Framer Motion
- **Streaming:** Server-Sent Events (SSE)

### Observability
- **Logging:** structlog (JSON output)
- **Tracing:** OpenTelemetry (OTLP)
- **Metrics:** Prometheus client
- **Testing:** pytest with async support

### Deployment
- **Containerization:** Docker + Docker Compose
- **Reverse Proxy:** Nginx
- **Security:** JWT, bcrypt, HTTPS ready

---

## Development Workflow

### Local Setup (Quick Start)

```bash
# 1. Clone & setup
git clone <repo>
cd Context\ Rag

# 2. Install backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Install frontend
cd ../frontend
npm install

# 4. Start services (Docker)
cd ..
docker-compose up

# 5. Run backend locally (for dev)
make dev

# 6. Run frontend locally (for dev)
cd frontend && npm run dev
```

### Makefile Commands

```bash
make install          # Install all dependencies
make dev              # Run API locally
make dev-worker       # Run worker locally
make test             # Run all tests
make lint             # Lint code
make format           # Format code
make up               # Start Docker services
make down             # Stop Docker services
make build            # Build images
make init             # Quick start (build + up)
```

### Environment Variables

**Critical Variables:**
```bash
NVIDIA_API_KEY=your_key_here
POSTGRES_PASSWORD=secure_password
JWT_SECRET_KEY=your_secret

# Services
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
QDRANT_HOST=localhost
QDRANT_PORT=6333
REDIS_HOST=localhost
REDIS_PORT=6379
```

---

## Service Dependencies & Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (React)                         │
│  Pages: Login, Chat, Documents                                  │
│  Components: ChatInterface, SourcePanel, DocumentManager        │
│  State: Zustand (auth, chat, documents)                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
                    HTTP/SSE (Axios)
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                      API Layer (FastAPI)                         │
│  /auth/login  /chat  /ingest  /documents  /reports              │
│  Middleware: CORS, Error Handling, Rate Limiting                │
└────────────────────────────┬────────────────────────────────────┘
                             │
          ┌──────────────────┼──────────────────┬─────────────┐
          │                  │                  │             │
          ▼                  ▼                  ▼             ▼
    ┌──────────┐      ┌──────────┐      ┌────────────┐  ┌────────┐
    │Workflow/ │      │Services/ │      │Ingestion/  │  │Database│
    │Orchestr  │      │Retrieval │      │Embedding   │  │Layer   │
    └──────────┘      └──────────┘      └────────────┘  └────────┘
          │                  │                  │             │
          └──────────────────┼──────────────────┴──────────┬──┘
                             │                             │
    ┌────────────────────────┼─────────────────────────────▼──┐
    │      External Services & Infrastructure                   │
    ├────────────────────────────────────────────────────────┤
    │ ┌─────────────────┐  ┌──────────────┐  ┌────────────┐  │
    │ │ NVIDIA NIM APIs │  │ PostgreSQL   │  │ Qdrant VDB │  │
    │ │ (LLM, Embed,    │  │ (Metadata,   │  │ (Vectors)  │  │
    │ │  Reranker)      │  │  Sessions)   │  │            │  │
    │ └─────────────────┘  └──────────────┘  └────────────┘  │
    │ ┌──────────────┐  ┌──────────────┐  ┌────────────────┐ │
    │ │ Redis        │  │ MinIO        │  │ Neo4j          │ │
    │ │ (Cache,      │  │ (Documents,  │  │ (Knowledge     │ │
    │ │  Queue)      │  │  Assets)     │  │  Graph)        │ │
    │ └──────────────┘  └──────────────┘  └────────────────┘ │
    └────────────────────────────────────────────────────────┘
```

---

## Common Development Tasks

### Adding a New API Endpoint

1. **Create request/response schema:**
   ```python
   # backend/schemas/your_schema.py
   class YourRequest(BaseModel):
       field: str
   ```

2. **Add route handler:**
   ```python
   # backend/api/your_routes.py
   @router.post("/your-endpoint")
   async def your_endpoint(request: YourRequest):
       return {"result": "..."}
   ```

3. **Register in main.py:**
   ```python
   app.include_router(your_routes.router, tags=["your-tag"])
   ```

### Adding a New Service

1. **Create service class:**
   ```python
   # backend/services/your_service.py
   class YourService:
       async def do_something(self):
           pass
   ```

2. **Register in dependency injection:**
   ```python
   # backend/core/dependency_injection.py
   def get_your_service() -> YourService:
       return YourService()
   ```

3. **Use in routes:**
   ```python
   @router.get("/...")
   async def endpoint(service: YourService = Depends(get_your_service)):
       return await service.do_something()
   ```

### Adding a New Frontend Component

1. **Create component:**
   ```typescript
   // frontend/src/components/YourComponent.tsx
   export const YourComponent: React.FC = () => {
       return <div>Your Component</div>;
   };
   ```

2. **Use in page:**
   ```typescript
   // frontend/src/pages/ChatPage.tsx
   import { YourComponent } from '../components/YourComponent';

   export const ChatPage = () => {
       return <YourComponent />;
   };
   ```

### Running Tests

```bash
# All tests
pytest

# Specific test file
pytest backend/tests/unit/test_retrieval_service.py

# With coverage
pytest --cov=backend

# Specific test
pytest -k "test_search"
```

---

## Performance Tips

### Query Optimization
- ✅ Use `top_k_retrieval` parameter (12-20)
- ✅ Enable reranking for small result sets
- ✅ Cache embeddings with 24-hour TTL
- ✅ Batch embedding requests when possible

### Database Optimization
- ✅ Use connection pooling (20-30 connections)
- ✅ Add indexes on frequently queried columns
- ✅ Use EXPLAIN ANALYZE for slow queries
- ✅ Implement pagination (limit 20-100)

### Vector Search Optimization
- ✅ Use `HNSW` index in Qdrant
- ✅ Configure `ef` parameter (100-200)
- ✅ Use metadata filtering to reduce search space
- ✅ Consider approximate search (trade accuracy for speed)

### API Optimization
- ✅ Enable response compression (gzip)
- ✅ Use streaming for large responses
- ✅ Implement result caching
- ✅ Batch API calls when possible

---

## Common Issues & Debugging

| Issue | Cause | Solution |
|-------|-------|----------|
| Slow queries (>5s) | Poor vector search performance | Check Qdrant index, increase `top_k`, enable caching |
| Memory leaks | Long-running connections | Add connection timeouts, implement connection pooling |
| Duplicate embeddings | Missing deduplication | Check embedding caching logic |
| High API costs | Too many API calls | Implement batching, improve caching strategy |
| Database connection timeout | Pool exhaustion | Increase pool size, check for idle connections |

---

## Key Configuration Parameters

### RAG Settings (`backend/core/config.py`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `CHUNK_SIZE` | 768 | Tokens per chunk |
| `CHUNK_OVERLAP` | 100 | Overlap between chunks |
| `TOP_K_RETRIEVAL` | 12 | Chunks to retrieve |
| `RERANK_TOP_K` | 6 | Chunks after reranking |
| `MAX_CONTEXT_TOKENS` | 6144 | Max context for LLM |
| `HYBRID_SEARCH_ENABLED` | true | Use hybrid search |
| `ENABLE_RERANKING` | true | Enable reranking |

### Performance Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| `API_WORKERS` | 4 | Worker processes |
| `DB_POOL_SIZE` | 20 | DB connections |
| `CACHE_TTL_SECONDS` | 86400 | Cache duration |
| `RATE_LIMIT_REQUESTS` | 100 | Per time window |
| `RATE_LIMIT_WINDOW` | 3600 | Time window (seconds) |

---

## Useful Commands Reference

### Docker
```bash
docker-compose up              # Start all services
docker-compose down            # Stop all services
docker-compose logs -f         # View logs
docker-compose ps              # Check status
docker exec -it api bash       # Shell into API
```

### Python/Backend
```bash
python -m pytest               # Run tests
python -m black backend        # Format code
python -m isort backend        # Sort imports
python -m mypy backend         # Type check
```

### Frontend
```bash
npm run dev                    # Development server
npm run build                  # Production build
npm run preview               # Preview build
npm run lint                  # Lint code
```

### Database
```bash
psql -U postgres -h localhost -d ragdb  # Connect to PostgreSQL
# Then: \dt - list tables, \d table_name - describe table
```

---

## Learning Resources

### Architecture Overview
- See: `Architecture.md` (73KB detailed document)
- See: `IMPLEMENTATION_PLAN_V3.md` (implementation details)

### API Documentation
- Interactive: http://localhost:8000/docs (Swagger UI)
- Alternative: http://localhost:8000/redoc (ReDoc)

### Code Examples
- View: `backend/tests/integration/` (example workflows)
- View: `backend/examples/` (if available)

---

## Summary

This is a **production-grade RAG system** with:
- ✅ Robust async architecture (FastAPI)
- ✅ Advanced document processing with multiple strategies
- ✅ Intelligent query routing and multi-hop reasoning
- ✅ Hybrid semantic + keyword search with reranking
- ✅ Real-time streaming responses
- ✅ Comprehensive observability
- ✅ Enterprise security features
- ✅ Multi-output report generation

**Next Steps:**
1. Review the `FUTURE_PLAN.md` for strategic direction
2. Start with Phase 1 (Q1 2026) optimizations
3. Refer to `Architecture.md` for detailed design decisions
4. Use Makefile for development commands
5. Check `/docs` endpoint for API documentation

---

**Version:** 1.0
**Last Updated:** February 27, 2026
