<div align="center">

<img src="./assets/images/mascot.png" alt="Bodham Mascot" width="160"/>

# Bodham Retrieval Engine

**A pluggable enterprise retrieval engine: hybrid search, reranking, planned multi-hop retrieval, cited answers, traces — on your own Qdrant index today, on Microsoft Foundry IQ or any MCP knowledge server tomorrow.**

[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Qdrant](https://img.shields.io/badge/Qdrant-hybrid-DC244C.svg)](https://qdrant.tech)
[![NVIDIA NIM](https://img.shields.io/badge/NVIDIA-NIM-76B900.svg?logo=nvidia)](https://build.nvidia.com)
[![Tests](https://img.shields.io/badge/tests-204%20passing-brightgreen.svg)](#tests)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

</div>

---

## What it does

Ask a question; Bodham routes it, plans it, retrieves evidence from the configured **knowledge backend**, writes one answer with validated `[n]` citations, and records a trace you can audit.

```
question ─▶ route ─▶ plan ─▶ retrieve (parallel) ─▶ evidence [1..n] ─▶ synthesize once ─▶ answer + citations + trace
                                  │
                   ┌──────────────┼──────────────────┐
              local (Qdrant)  foundry_iq (Azure)   mock / your adapter
```

* **Hybrid retrieval** – dense NVIDIA embeddings + BM25 sparse vectors fused with Reciprocal Rank Fusion inside Qdrant, then NIM cross-encoder reranking.
* **Structure-aware ingestion** – PDF/DOCX/MD/TXT/HTML/CSV parsing, heading-aware chunks with contextual headers, tables kept intact, page-level citations.
* **Deterministic-first orchestration** – rules route chat / knowledge / action / clarification; only complex questions pay for an LLM plan (decomposition + alternate phrasings).
* **Grounded synthesis** – single generation from numbered evidence; citations that point nowhere are stripped; confidence is derived, not asserted.
* **Swappable backends** – `KNOWLEDGE_BACKEND=local|foundry_iq|mcp|mock`, optional fallback backend, per-request override. The Foundry IQ adapter speaks the 2026 Azure AI Search agentic-retrieval API and forwards the user token for ACL trimming; the MCP adapter consumes any MCP knowledge server (Foundry IQ's `/mcp`, another Bodham, Qdrant MCP, Pinecone, Ragie...).
* **MCP server** – Bodham is itself an MCP server at `/mcp` (streamable HTTP) exposing `knowledge_retrieve`, `list_documents` and `list_backends`, so Foundry Agent Service, Claude, LangGraph or any MCP client can use it as a knowledge source.
* **Permission model** – every chunk carries ACL principals (`user:`, `tenant:`, `group:`, `public`); retrieval and document listing filters are derived from the verified token, never from the client, and anonymous callers only see public documents. Documents are uploaded as private, tenant or public and can be shared with groups.
* **Authentication** – local JWTs (with tenant, role and group claims and admin user management) or Microsoft Entra ID bearer tokens validated against the tenant JWKS (`AUTH_MODE=entra|both`).
* **Observability & evaluation** – per-query traces (`/traces`), feedback, an offline eval harness (hit@k, MRR, context recall, citation rate, LLM-judged faithfulness) and a sample dataset.
* **Typed streaming UI contract** – SSE events `progress`, `evidence`, `answer_delta`, `done`; the bundled React UI shows the live stage and confidence.

See [`docs/ARCHITECTURE_V3.md`](docs/ARCHITECTURE_V3.md) for the design and [`docs/MARKET_RESEARCH.md`](docs/MARKET_RESEARCH.md) for the October 2026 landscape (Foundry IQ, Bedrock, Vertex, OpenAI, NVIDIA, open-source frameworks and techniques) that shaped it.

---

## Quick start

### 1. Zero-infrastructure run (SQLite + embedded Qdrant)

```bash
git clone https://github.com/mrigankad/Dexter-retrival-engine.git && cd Dexter-retrival-engine
cp .env.example .env                 # set NVIDIA_API_KEY (https://build.nvidia.com)
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && cd ..
make dev-local                       # API on http://localhost:8000  (Swagger at /docs)
cd frontend && npm install && npm run dev   # UI on http://localhost:3000
```

Login with `admin / admin123`, upload a document, ask a question.

### 2. Full stack with Docker

```bash
cp .env.example .env && make init    # api, worker, postgres, qdrant, redis, frontend
docker compose --profile graph --profile storage up -d   # optional Neo4j + MinIO
```

### 3. Use Bodham from an agent over MCP

```bash
MCP_API_TOKEN=<long random string>          # or use a user's Bodham/Entra bearer token
# MCP endpoint: http://localhost:8000/mcp   (Authorization: Bearer ...)
```

Register the URL as an MCP server in Foundry Agent Service, Claude Desktop/Code, LangGraph or Microsoft Agent Framework and allow the `knowledge_retrieve` tool.

### 4. Use Microsoft Foundry IQ as the knowledge layer

```bash
KNOWLEDGE_BACKEND=foundry_iq
AZURE_SEARCH_ENDPOINT=https://<service>.search.windows.net
AZURE_SEARCH_API_KEY=...             # or AZURE_SEARCH_BEARER_TOKEN
FOUNDRY_IQ_KNOWLEDGE_BASE=<knowledge base name>
FOUNDRY_IQ_REASONING_EFFORT=low      # minimal | low | medium
```

Ingestion then stays on the Azure side (Blob / SharePoint / OneLake knowledge sources); Bodham plans, synthesises and cites. Check `GET /knowledge/backends` and `GET /knowledge/backends/foundry_iq/health`. Alternatively point the generic MCP adapter at the knowledge base's MCP endpoint: `KNOWLEDGE_BACKEND=mcp`, `MCP_SERVER_URL=https://<svc>.search.windows.net/knowledgebases/<kb>/mcp?api-version=2026-08-01-preview`, `MCP_TOOL_NAME=knowledge_base_retrieve`, `MCP_AUTH_TOKEN=<Entra token>`.

---

## API (also under `/v1`)

| Endpoint | Purpose |
|---|---|
| `POST /chat` | SSE stream (default) or JSON answer; body `{query, session_id?, use_rag, document_ids?, top_k?, reasoning_effort?, backend?}` |
| `GET /chat/sessions`, `GET/DELETE /chat/history/{id}`, `POST /chat/feedback` | conversation memory and feedback |
| `POST /ingest` (form fields `visibility`, `groups`), `GET /documents`, `GET /documents/{id}`, `GET /documents/{id}/chunks`, `PUT /documents/{id}/sharing`, `POST /documents/{id}/reprocess`, `DELETE /documents/{id}`, `GET /files/{id}` | document lifecycle and sharing |
| `/mcp` | MCP server (streamable HTTP, bearer auth): tools `knowledge_retrieve`, `list_documents`, `list_backends` |
| `GET /knowledge/backends`, `GET /knowledge/backends/{name}/health`, `POST /knowledge/retrieve` | backends and the raw retrieve tool (same contract a future MCP tool exposes) |
| `GET /traces`, `GET /traces/{trace_id}` | audit: intent, plan, tool calls, latency, tokens |
| `POST /evaluations/run`, `GET /evaluations/{message_id}` | eval harness / per-message scores |
| `POST /auth/login|register|refresh`, `GET /auth/me`, `GET /auth/users`, `PUT /auth/users/{username}` (admin), `GET /health` | auth, user management and health |

SSE events: `start`, `progress {stage,label}`, `evidence [...]`, `sources [...]`, `answer_delta {text}`, `warning`, `done {answer_id,confidence,latency_ms,trace_id,citations,usage}`, `metadata {message_id}`, `error`.

---

## Tests

```bash
cd backend && python -m pytest -q        # 204 tests, no external services (SQLite, in-memory Qdrant, fake models)
make eval DATASET=evals/datasets/sample.json
```

---

## Repository layout

```
backend/
  main.py                 FastAPI app (routes at legacy paths and /v1)
  src/contracts/          typed contracts (retrieval, evidence, plan, answer, events)
  src/core/               settings, logging, JWT + Entra auth, access control, DI
  src/infrastructure/     database (PostgreSQL/SQLite), vector_store (Qdrant hybrid), cache (Redis)
  src/services/llm/       NVIDIA NIM chat / embeddings / reranker clients
  src/ingestion/          parsers, hierarchical chunker, pipeline, worker
  src/retrieval/          hybrid retriever, RRF, context builder
  src/knowledge/          KnowledgeAdapter + local / foundry_iq / mcp / mock + registry
  src/mcp_server/         MCP server (knowledge_retrieve, list_documents, list_backends) mounted at /mcp
  src/orchestrator/       router, planner, executor, synthesizer, engine
  src/evaluation/         offline eval harness
  src/api/v1/             HTTP routes
  src/agents/             legacy multi-agent experiments (/api/agents)
  tests/                  unit + integration (HTTP via ASGI)
frontend/                 React + TypeScript UI (Vite, Tailwind, Zustand)
docs/                     ARCHITECTURE_V3.md, MARKET_RESEARCH.md, research/, earlier plans
evals/                    datasets and reports
docker/, docker-compose.yml, Makefile, .env.example
```

## Configuration

Every setting in [`backend/src/core/config.py`](backend/src/core/config.py) is an environment variable; [`.env.example`](.env.example) documents the important ones. Highlights: `KNOWLEDGE_BACKEND`, `NVIDIA_*_MODEL` (verify IDs on build.nvidia.com; the client falls back on 404/410/429), `QDRANT_MODE=server|memory|path`, `USE_SQLITE`, `INGESTION_MODE=queue|inline`, `RERANKER_BACKEND=nvidia|local|none`, `CHUNK_SIZE`, `RERANK_TOP_K`, `MAX_CONTEXT_TOKENS`.

## Roadmap

Connectors (SharePoint, Google Drive, Confluence, S3) · structured-data `data.query` tool with AST-validated read-only SQL · CRAG-style iterative retrieval and graph tier behind the router · OTel/Langfuse export · notebooks, summaries, follow-ups · OAuth 2.1 on the MCP server. Details and status: [`BUILD_STATUS.md`](BUILD_STATUS.md), [`docs/ARCHITECTURE_V3.md`](docs/ARCHITECTURE_V3.md).

## License

MIT.
