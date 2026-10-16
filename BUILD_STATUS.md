# BUILD_STATUS

_Last updated: 2026-10-16 (branch `claude/gallant-lovelace-lujn7r`)_

## State of the repository before this iteration

* `main.py` imported six route modules and a database session manager that had been deleted in commit `dad9304` ("clean up legacy code structure"); the API could not start.
* Four services existed as byte-identical duplicates under `services/llm/` and `services/{retrieval,embedding,evaluation}/`.
* "Hybrid search" was a keyword substring boost over dense results; no sparse index, no fusion.
* The multi-agent `SearchAgent` called `retrieve()` expecting a dict and would have crashed on the list it returned.
* Tests imported deleted modules (`workflow.rag_pipeline`) and patched non-existent paths.

## Completed in this iteration

| Area | What |
|---|---|
| Research | `docs/MARKET_RESEARCH.md` + three cited reports in `docs/research/` (managed platforms incl. Foundry IQ, open-source techniques, interop/memory/governance). |
| Contracts | `src/contracts/` — retrieval, evidence, plan, answer, trace, SSE events, ingestion. |
| Config | `src/core/config.py` — backend selection, Foundry IQ, SQLite/in-memory modes, retrieval knobs, 2026 NIM model IDs with fallback chain. |
| Infrastructure | Portable SQLAlchemy models (+ `traces`, `feedback`), lazy async engine, Qdrant hybrid store (named dense + sparse, RRF, payload filters, memory/path/server), stateless BM25 sparse encoder, optional Redis. |
| Models | NIM chat (streaming, JSON mode, usage, 404/410/429 fallback), embeddings (batched, cached), reranker (NIM / local / none). |
| Knowledge adapters | `KnowledgeAdapter` + local / Foundry IQ (2026-08-01-preview surface, extractive mode, ACL header) / mock + registry with fallback. |
| Ingestion | Parsers (Docling→PyMuPDF→pypdf, DOCX with headings+tables, MD/TXT/HTML/CSV), hierarchical chunker with contextual headers and table chunks, pipeline, worker with inline fallback, reprocess/delete. |
| Retrieval | Multi-query hybrid retriever, RRF, dedupe, rerank, context builder with numbered evidence. |
| Orchestrator | Router (rules + LLM), planner (decomposition + alternates, cached), executor (parallel, budgets, fallback), synthesizer (validated citations, confidence), engine (typed SSE stream, traces). |
| API | health, auth (DB users), chat (SSE/JSON, sessions, history, feedback, per-request backend override), documents (upload/list/get/chunks/file/reprocess/delete), knowledge (backends, health, raw retrieve), traces, evaluations; mounted at legacy paths and `/v1`. |
| Evaluation | `src/evaluation` harness + `scripts/run_eval.py` + `evals/datasets/sample.json`. |
| Frontend | Handles `progress`, `evidence`, `answer_delta`, `warning`, `done` events; shows live stage label and confidence/intent/latency badges; `tsc` + `vite build` pass. |
| Packaging | Core vs optional requirements, Python 3.12 images, compose with profiles for Neo4j/MinIO, `.env.example`, Makefile (`dev-local`, `test`, `eval`). |
| Tests | 204 passing (`cd backend && python -m pytest -q`): unit (sparse/fusion, chunker/parsers, router/synthesis, adapters incl. Foundry IQ over a mock transport), integration (pipeline, engine, eval harness, full HTTP API via ASGI), legacy agent tests repaired. |

## Commands

```bash
# tests (no external services needed)
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && python -m pytest -q

# zero-infra dev server (needs NVIDIA_API_KEY in .env)
make dev-local            # http://localhost:8000/docs
cd frontend && npm install && npm run dev

# full stack
cp .env.example .env && make init

# evaluation
make eval DATASET=evals/datasets/sample.json
```

## Decisions

* One orchestrator with tools, not an agent swarm (legacy agents kept under `/api/agents`).
* Synthesis happens once, in our orchestrator, even for Foundry IQ (`outputMode=extractiveData`), so citations are validated uniformly.
* No new vector DB is introduced when `KNOWLEDGE_BACKEND=foundry_iq`; Qdrant is only used by the local backend.
* Default NIM model IDs follow the October 2026 catalogue; verify on build.nvidia.com (the client falls back on 404/410/429).

## Not done / blockers

* Not verified against live NVIDIA or Azure endpoints from this sandbox (no API keys); all model-facing code is exercised with fakes and mock transports.
* Docker images were not built here (no daemon access in the session); the Dockerfiles install from the new requirements files.
* Docling is optional (`requirements-optional.txt`); the default image parses PDFs with pypdf unless `INSTALL_OPTIONAL=true`.
* Structured-data (`data.query`), MCP server, ACL enforcement and connectors are designed (see `docs/ARCHITECTURE_V3.md` §6) but not implemented.

## Next actions

1. Add `NVIDIA_API_KEY`, run `make dev-local`, upload a PDF, ask a question, inspect `/traces`.
2. Run `make eval` after indexing `evals/datasets` sources; grow the dataset to 150+ questions.
3. Implement the MCP server + ACL filter injection (v2 items 1–2).
