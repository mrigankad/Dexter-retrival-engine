# 🚀 Dexter Retrieval Agent

A production-ready, enterprise-grade **Retrieval Augmented Generation (RAG)** system powered by **NVIDIA NIM APIs**.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Docker Network                           │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐  ┌──────────┐  ┌─────────┐           │
│  │ FastAPI │  │ Qdrant  │  │PostgreSQL│  │  Redis  │           │
│  │   API   │◄─┤ Vectors │  │   Chat   │  │  Cache  │           │
│  └────┬────┘  └─────────┘  └──────────┘  └─────────┘           │
│       │       ┌──────────────┐                                  │
│       └──────►│  Ingestion   │                                  │
│               │    Worker    │                                  │
│               └──────────────┘                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   NVIDIA NIM    │
                    │  - LLM API      │
                    │  - Embeddings   │
                    │  - Reranking    │
                    └─────────────────┘
```

## ✨ Features

- 🤖 **Multi-Pipeline Routing** - Intelligent query classification (RAG/Direct LLM/Tools)
- 📄 **Document Ingestion** - PDF, DOCX, TXT support with semantic chunking
- 🔍 **Vector Search** - Qdrant-powered similarity search with reranking
- 💬 **Streaming Chat** - Server-Sent Events (SSE) for real-time responses
- 🔐 **JWT Authentication** - Secure API access with rate limiting
- 📊 **Observability** - Structured JSON logging with request tracing
- 🐳 **Fully Dockerized** - Single command deployment

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- NVIDIA API Key (get one at [build.nvidia.com](https://build.nvidia.com))

### 1. Clone & Configure

```bash
# Clone the repository
cd RAG-POC

# Copy environment template
cp .env.example .env

# Edit .env and add your NVIDIA API key
# NVIDIA_API_KEY=nvapi-xxx
```

### 2. Start Services

```bash
# Build and start all services
docker compose up -d

# Or use the Makefile
make init
```

### 3. Verify

```bash
# Check service status
docker compose ps

# View logs
docker compose logs -f api

# Health check
curl http://localhost:8000/health
```

## 📡 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with service status |
| `/chat` | POST | Chat with streaming support |
| `/ingest` | POST | Upload and ingest documents |
| `/documents` | GET | List ingested documents |
| `/auth/login` | POST | Authenticate and get JWT token |

### Chat Example

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is machine learning?",
    "stream": false,
    "use_rag": true
  }'
```

### Document Ingestion

```bash
curl -X POST http://localhost:8000/ingest \
  -H "Authorization: Bearer <token>" \
  -F "file=@document.pdf"
```

## 🧪 Testing

```bash
# Run all tests
make test

# Run unit tests only
make test-unit

# Run integration tests
make test-integration
```

## 📁 Project Structure

```
RAG-POC/
├── backend/
│   ├── api/               # FastAPI routes
│   ├── core/              # Config, logging, security
│   ├── workflow/          # Orchestrator, RAG pipeline
│   ├── services/          # NVIDIA, vector store, retrieval
│   ├── ingestion/         # Document processing
│   ├── db/                # Database models
│   ├── schemas/           # Pydantic models
│   ├── utils/             # Utilities
│   ├── tests/             # Test suite
│   └── main.py            # App entry point
├── docker/
│   ├── api/Dockerfile
│   └── ingestion/Dockerfile
├── scripts/
│   └── init_db.sql
├── docker-compose.yml
├── Makefile
└── README.md
```

## ⚙️ Configuration

All configuration is via environment variables. See `.env.example` for all options.

### Key Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `NVIDIA_API_KEY` | Your NVIDIA API key | Required |
| `NVIDIA_LLM_MODEL` | LLM model to use | `meta/llama-3.1-70b-instruct` |
| `NVIDIA_EMBED_MODEL` | Embedding model | `nvidia/nv-embedqa-e5-v5` |
| `CHUNK_SIZE` | Document chunk size | `512` |
| `TOP_K_RETRIEVAL` | Number of chunks to retrieve | `5` |

## 🔧 Development

### Local Development

```bash
# Install dependencies
cd backend
pip install -r requirements.txt

# Run locally (requires services running)
python -m uvicorn main:app --reload
```

### API Documentation

When running in development mode, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 🐳 Docker Services

| Service | Port | Description |
|---------|------|-------------|
| `api` | 8000 | FastAPI backend |
| `qdrant` | 6333-6334 | Vector database |
| `postgres` | 5432 | PostgreSQL database |
| `redis` | 6379 | Cache & rate limiting |
| `ingestion-worker` | - | Background document processor |

## 📊 Monitoring

### Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api
```

### Health Check

```bash
curl http://localhost:8000/health
```

## 🔐 Security

- JWT-based authentication
- Rate limiting via Redis
- API key stored securely in environment
- Non-root Docker containers

## 🚀 Production Deployment

1. Update `.env` with production values
2. Set `APP_ENV=production` and `DEBUG=false`
3. Use strong `JWT_SECRET_KEY`
4. Configure proper CORS origins
5. Set up monitoring and alerting

```bash
make prod-build
make prod-up
```

## 📝 License

MIT License

## 🙏 Acknowledgments

- [NVIDIA NIM](https://build.nvidia.com) - LLM, Embeddings, Reranking APIs
- [FastAPI](https://fastapi.tiangolo.com) - Modern Python web framework
- [Qdrant](https://qdrant.tech) - Vector search engine
- [LlamaIndex](https://llamaindex.ai) - RAG framework
