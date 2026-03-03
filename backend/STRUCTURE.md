# Backend Folder Structure - Professional Layout

## Overview
Enterprise-grade Python project organization with clear separation of concerns, scalability, and maintainability.

```
backend/
├── src/                              # Main source code
│   ├── agents/                       # Multi-agent system (Phase 1-4)
│   │   ├── base/                     # Base classes (Agent, Memory)
│   │   ├── core/                     # Core 4 agents (Search, Analysis, Verification, Synthesis)
│   │   ├── domain/                   # Domain experts (Tech, Business, Healthcare, Legal)
│   │   ├── coordinator/              # Pipeline orchestration
│   │   └── communication/            # Inter-agent messaging
│   │
│   ├── api/                          # HTTP API layer
│   │   ├── v1/                       # API v1 routes
│   │   ├── schemas/                  # Pydantic models
│   │   └── middleware/               # Auth, error handling, rate limiting
│   │
│   ├── core/                         # Core utilities
│   │   ├── config.py                 # Configuration management
│   │   ├── logger.py                 # Logging setup
│   │   ├── exceptions.py             # Custom exceptions
│   │   └── constants.py              # Application constants
│   │
│   ├── infrastructure/               # External services layer
│   │   ├── database/                 # PostgreSQL connections & models
│   │   ├── cache/                    # Redis caching
│   │   ├── vector_store/             # Qdrant vector database
│   │   └── storage/                  # MinIO file storage
│   │
│   ├── services/                     # Business logic layer
│   │   ├── llm/                      # LLM services (NVIDIA NIM)
│   │   ├── retrieval/                # Document retrieval & reranking
│   │   ├── embedding/                # Text embedding
│   │   ├── knowledge/                # Knowledge graphs & semantic search
│   │   └── evaluation/               # RAGAS evaluation metrics
│   │
│   ├── workflows/                    # High-level orchestration
│   │   ├── query/                    # Query processing pipelines
│   │   └── ingestion/                # Document ingestion pipelines
│   │
│   └── utils/                        # Utility functions
│       ├── validators.py
│       ├── formatters.py
│       └── helpers.py
│
├── tests/                            # Test suite (mirrored src structure)
│   ├── conftest.py                   # Pytest configuration
│   ├── fixtures/                     # Shared test fixtures & mocks
│   ├── unit/                         # Unit tests (fast, mocked)
│   │   ├── agents/
│   │   ├── services/
│   │   ├── api/
│   │   └── workflows/
│   └── integration/                  # Integration tests (real services)
│       ├── agents/
│       ├── workflows/
│       └── end_to_end/
│
├── config/                           # Configuration files
│   ├── settings.py                   # Pydantic settings
│   └── logging.yaml                  # Logging config
│
├── scripts/                          # Utility scripts
│   ├── seed_database.py
│   ├── migrate_data.py
│   └── generate_docs.py
│
├── docs/                             # Documentation
│   ├── ARCHITECTURE.md               # System design
│   ├── API.md                        # API docs
│   ├── AGENTS.md                     # Agent docs
│   └── DEPLOYMENT.md                 # Deployment guide
│
├── main.py                           # Application entry point
├── requirements.txt                  # Python dependencies
├── .env.example                      # Environment template
├── .gitignore                        # Git ignore
├── pytest.ini                        # Pytest config
└── STRUCTURE.md                      # This file
```

## Key Principles

1. **Clear Separation of Concerns**
   - `src/agents/` - Agent logic only
   - `src/api/` - HTTP endpoints only
   - `src/services/` - Business logic only
   - `src/infrastructure/` - External dependencies only

2. **Testability**
   - Mirror structure in `tests/`
   - Unit tests use mocks (fast)
   - Integration tests use real services (slow)

3. **Scalability**
   - Modular design for easy extension
   - Services can be independently deployed
   - Clear dependency boundaries

4. **Maintainability**
   - Self-documenting structure
   - PEP 8 conventions
   - No circular dependencies
   - Clear import paths

## Import Guidelines

```python
# ✅ Good
from src.agents.base import Agent
from src.services.llm import NvidiaLLMService
from src.infrastructure.database import get_session
from src.core.config import settings

# ❌ Bad
from agents import *
from .. import services
```

## Migration Status

- [x] Foundation created (Phase 1)
- [x] Core agents built (Phase 2)
- [x] Coordinator & API added (Phase 3)
- [x] Domain experts added (Phase 4)
- [ ] Refactor to src/ structure (Phase 5)
- [ ] Support agents (Phase 5)
- [ ] Frontend integration (Phase 6)
- [ ] Production deployment (Phase 7)
