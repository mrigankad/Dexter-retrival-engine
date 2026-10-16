# Dexter Retrieval Engine — Architecture v3

Dexter is a pluggable enterprise retrieval engine: it ingests documents into a hybrid index, routes and plans questions, retrieves evidence from a swappable **knowledge backend**, synthesises one cited answer, and records a trace for every query. The same orchestrator can run on the built-in Qdrant index today and on Microsoft Foundry IQ (Azure AI Search agentic retrieval) or any MCP knowledge server tomorrow.

```
                      ┌──────────────────────────────────────────────────────────────┐
  React UI  ──SSE──▶  │  FastAPI  (/chat, /ingest, /documents, /knowledge, /traces)  │
                      └───────────────┬──────────────────────────────┬───────────────┘
                                      │                              │ upload
                                      ▼                              ▼
                      ┌──────────────────────────────┐   ┌──────────────────────────┐
                      │  RetrievalEngine (orchestrator)│   │  Ingestion pipeline       │
                      │  route → plan → execute →      │   │  parse → chunk (+context  │
                      │  evidence → synthesize → trace │   │  headers) → dense+sparse  │
                      └───────────────┬────────────────┘   │  embed → Qdrant → DB rows │
                                      │ knowledge.retrieve   └─────────────┬────────────┘
                                      ▼                                    │
                      ┌──────────────────────────────┐                     │
                      │  KnowledgeAdapter registry    │                     │
                      │  local │ foundry_iq │ mock    │◀────────────────────┘
                      └───┬───────────┬──────────────┘
                          │           │
                 Qdrant hybrid    Azure AI Search
                 (dense+BM25,     knowledge base
                 RRF, rerank)     (agentic retrieval)
```

## 1. Layers (backend/src)

| Package | Responsibility |
|---|---|
| `contracts/` | Pydantic contracts shared by every layer: `RetrievalRequest/Result/RetrievedChunk`, `Evidence`, `QueryPlan`, `Answer`, `TraceRecord`, SSE events, ingestion models. Backends are swappable because callers only see these. |
| `core/` | Settings (`config.py`, every knob is an env var), structured logging, JWT security, FastAPI dependencies. |
| `infrastructure/` | `database/` (SQLAlchemy async; PostgreSQL or SQLite), `vector_store/` (Qdrant hybrid store + stateless BM25 sparse encoder), `cache/` (optional Redis). |
| `services/llm/` | NVIDIA NIM clients: chat (streaming, JSON mode, usage, model fallback chain), embeddings (batched, cached, `input_type` aware), reranker (NIM `/reranking`, optional local CrossEncoder, or none). |
| `ingestion/` | Parsers (PDF via Docling → PyMuPDF → pypdf, DOCX, TXT/MD/HTML/CSV), hierarchical chunker, pipeline, Redis worker with inline fallback. |
| `retrieval/` | `HybridRetriever` (multi-query → Qdrant prefetch+RRF → dedupe → rerank), RRF/dedupe helpers, `ContextBuilder` (numbered evidence within a token budget). |
| `knowledge/` | `KnowledgeAdapter` ABC + `LocalKnowledgeAdapter`, `FoundryIQAdapter`, `MockKnowledgeAdapter`, registry (`KNOWLEDGE_BACKEND`, `KNOWLEDGE_FALLBACK_BACKEND`). |
| `orchestrator/` | `QueryRouter` (rules first, cheap LLM for the ambiguous middle), `QueryPlanner` (bounded decomposition + alternate phrasings, cached), `PlanExecutor` (parallel steps, budgets, fallback backend, cross-step RRF), `Synthesizer` (single grounded generation, citation validation, confidence), `RetrievalEngine` (streams typed events, persists traces). |
| `evaluation/` | Offline harness: hit@k, MRR, context recall, answer substring recall, citation rate, optional LLM-judged faithfulness/relevancy, latency percentiles. |
| `api/v1/` | Routes (also mounted under `/v1`): health, auth, chat (SSE + JSON, sessions, history, feedback), documents, knowledge backends + raw `retrieve`, traces, evaluations. The legacy multi-agent routes (`/api/agents`) remain for experimentation. |
| `agents/` | Legacy multi-agent package (search/analysis/verification/synthesis + persona experts) kept intact; its `SearchAgent` now calls the adapter layer. |

## 2. Query path

1. **Guardrails** – input check (prompt-injection / PII patterns) when `GUARDRAILS_ENABLED`.
2. **Route** – deterministic rules classify `CHAT`, `KNOWLEDGE`, `ACTION` (blocked), `CLARIFICATION`; query type (`lookup`, `comparative`, `temporal`, `causal`, `aggregation`, `analytical`) decides whether planning is worth an LLM call. Only ambiguous inputs hit the fast model.
3. **Plan** – simple questions become one `knowledge.retrieve` step. Complex ones are decomposed by the fast model into ≤ `MAX_SUB_QUERIES` atomic sub-questions plus ≤2 alternate phrasings (multi-query fusion on the first step). Backends that plan themselves (Foundry IQ at `low`/`medium`) skip this. Plans are cached by normalised query.
4. **Execute** – steps run in parallel against the adapter (fallback backend on error/empty), results are fused with RRF across steps, de-duplicated, and packed into numbered evidence `[1]..[n]` within `MAX_CONTEXT_TOKENS`.
5. **Synthesize once** – the model answers from the evidence only, citing `[n]`; markers that do not resolve are stripped, the cited evidence set is returned, and confidence (`high/medium/low`) is derived from reranker scores, citation coverage and "not found" phrasing.
6. **Trace** – intent, plan, tool calls (backend, latency, result counts), evidence count, token usage and confidence are stored in `traces` and returned as `trace_id`.

Streaming events (SSE): `start`, `progress{stage,label}`, `evidence[]`, `sources[]` (legacy shape), `answer_delta{text}`, `warning`, `done{answer_id,confidence,latency_ms,trace_id,citations,usage}`, `metadata{message_id,...}`, `error`.

## 3. Ingestion path

`parse_file` → `HierarchicalChunker` (section path from headings, ~`CHUNK_SIZE` tokens with sentence-aware overlap, tables kept whole as `table` chunks plus a summary chunk, contextual header `Document: … | Section: …` prepended to the *embedded* text only) → NIM dense embeddings (`input_type=passage`) + BM25 sparse vectors (hash-indexed, IDF applied by Qdrant) → `QdrantStore.upsert` (named vectors `dense` + `sparse`, payload: document_id, source, page, section_path, content_type, tenant/user) → `document_chunks` rows → document status/metadata. Optional: MinIO archive, Neo4j triplet extraction.

The worker (`python -m src.ingestion.worker`) consumes the Redis queue; without Redis (`INGESTION_MODE=inline`) uploads are processed as background tasks in the API process.

## 4. Knowledge adapters

```python
class KnowledgeAdapter(ABC):
    name: str
    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult: ...
    async def healthcheck(self) -> dict: ...
    def capabilities(self) -> AdapterCapabilities: ...   # hybrid_search, reranking, query_planning, ...
```

* **local** – `HybridRetriever` over Qdrant; honours `document_ids`, `tenant_id`, `user_id`, `content_types`, `page` and arbitrary payload filters.
* **foundry_iq** – `POST /knowledgebases('{kb}')/retrieve` with `outputMode=extractiveData`, reasoning effort from the request, OData `filterAddOn` for scope, `x-ms-query-source-authorization` for per-user ACL trimming, `references[]`/`activity[]` mapped to chunks and trace. Falls back across the three path styles Azure has shipped (`knowledgebases('x')`, `knowledgebases/x`, `agents/x`).
* **mock** – keyword overlap over in-memory documents; used by tests and offline demos.

Adding a backend = one class + one registry entry. `POST /knowledge/retrieve` exposes the same contract over HTTP (the future MCP tool).

## 5. Running modes

| Mode | Settings | External services |
|---|---|---|
| Tests | `APP_ENV=test` (set by `backend/conftest.py`) | none (SQLite, in-memory Qdrant, fake models) |
| Local, zero infra | `make dev-local` | NVIDIA API key only (SQLite, on-disk Qdrant, inline ingestion) |
| Docker | `make init` | PostgreSQL, Qdrant 1.19, Redis, worker; `--profile graph` adds Neo4j, `--profile storage` adds MinIO |
| Foundry IQ | `KNOWLEDGE_BACKEND=foundry_iq` + `AZURE_SEARCH_*`, `FOUNDRY_IQ_*` | Azure AI Search knowledge base (ingestion stays Azure-side) |

## 6. Roadmap

**v1 (this branch):** everything above, 204 tests, eval harness, sample dataset.

**v2 (next):**
1. MCP server (`mcp` SDK ≥ 2.3) exposing `knowledge_retrieve`, so Foundry Agent Service / Claude / any MCP client can use Dexter as a knowledge source; generic `McpRetriever` adapter for third-party servers.
2. Permission model: ACL principals stored on chunks at ingestion, mandatory filter injected from the verified JWT (never client-supplied), fail closed; Entra ID login.
3. Connectors: SharePoint/OneDrive, Google Drive, Confluence, S3/Blob, web crawl (Onyx-style connector ABC + scheduler).
4. Structured data tool (`data.query`): semantic model, NL→SQL, `sqlglot` AST policy (read-only, allowlists, limits), evidence type `sql` — the Bodham blueprint.
5. Retrieval tiers behind the router: CRAG-style relevance gating + iterative retrieval, RAPTOR-lite summaries for "summarise the whole document", LightRAG/HippoRAG graph tier for multi-hop, ColPali page retrieval for visual PDFs.
6. Observability: OTel GenAI spans → Langfuse/Phoenix; online RAGAS faithfulness sampling; cost per query by backend.
7. Product surface: notebooks/collections, source summaries, suggested follow-ups, report export, evidence drawer with highlight-to-source.
