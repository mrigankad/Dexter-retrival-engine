# Bodham Retrieval Engine — Architecture v3

Bodham is a pluggable enterprise retrieval engine: it ingests documents into a hybrid index, routes and plans questions, retrieves evidence from a swappable **knowledge backend**, synthesises one cited answer, and records a trace for every query. The same orchestrator can run on the built-in Qdrant index today and on Microsoft Foundry IQ (Azure AI Search agentic retrieval) or any MCP knowledge server tomorrow.

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
| `knowledge/` | `KnowledgeAdapter` ABC + `LocalKnowledgeAdapter`, `FoundryIQAdapter`, `McpKnowledgeAdapter` (any MCP knowledge server), `MockKnowledgeAdapter`, registry (`KNOWLEDGE_BACKEND`, `KNOWLEDGE_FALLBACK_BACKEND`). |
| `mcp_server/` | Bodham as an MCP server (streamable HTTP at `/mcp`, stateless, JSON responses): tools `knowledge_retrieve`, `list_documents`, `list_backends`; bearer auth via Bodham/Entra tokens or `MCP_API_TOKEN`; the caller's identity drives the same ACL filters as the HTTP API. |
| `connectors/` | Source connectors (`local_folder`, `web`, `s3`, `sharepoint`/OneDrive via Microsoft Graph, `google_drive`, `confluence`) behind one `Connector` ABC (`list_items`, `fetch`, `test_connection`, delta cursor); `ConnectorSyncService` diffs by version key + ACL, creates/updates/removes documents, enqueues ingestion with source-derived principals; in-process scheduler; admin API. |
| `data_gateway/` | The `data.query` tool: read-only connections (`DataConnectionManager`), schema discovery, semantic model (entities, metrics, synonyms, relationships, glossary, verified queries), relevant-table ranking, `SqlGenerator` (fast model, policy feedback retry), `SqlPolicy` (sqlglot AST), timed/capped execution, chart suggestion/validation; persistence + admin/query API. |
| `core/access.py`, `core/auth.py` | Principals (`public`, `tenant:<id>`, `user:<id>`, `group:<name>`), ACL derivation for documents, mandatory retrieval filters from the verified identity (fail closed); bearer verification for local JWTs and Entra ID tokens (JWKS cache). |
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
* **mcp** – generic MCP client: connects to `MCP_SERVER_URL`, calls `MCP_TOOL_NAME` (`knowledge_retrieve` for another Bodham, `knowledge_base_retrieve` for Foundry IQ), parses structured content, JSON text or plain text into chunks. Also accepts an in-process `MCPServer` for tests.
* **mock** – keyword overlap over in-memory documents; used by tests and offline demos.

Adding a backend = one class + one registry entry. `POST /knowledge/retrieve` and the MCP tool `knowledge_retrieve` expose the same contract.

## 4a. Permission model

* **Principals on chunks.** Ingestion writes an `acl` list on every Qdrant payload, computed from the document's owner, tenant, visibility (`private` → owner only, `tenant` → everyone in the tenant, `public` → anyone) and shared groups. `PUT /documents/{id}/sharing` changes it and re-indexes.
* **Filters from identity, never from the client.** `access_filters_for(token)` turns the verified JWT/Entra claims into `RetrievalFilters.principals` (`public`, `user:<id>`, `tenant:<id>`, `group:<g>`...). The Qdrant store adds a mandatory `acl` match-any condition; the mock adapter applies the same rule; Foundry IQ receives the caller's token in `x-ms-query-source-authorization`. Anonymous callers get `public` only. Admins and the MCP service token are tenant-scoped instead.
* **Same rule for metadata.** Document list/get/delete use `document_visibility_clause` (owner, public, tenant, or a shared group); only the owner or an admin can delete, reprocess or re-share.
* **Identity sources.** `AUTH_MODE=local` issues HS256 JWTs carrying `tenant_id`, `role`, `groups` (admins manage them via `PUT /auth/users/{username}`); `AUTH_MODE=entra` validates RS256 Entra ID tokens against the tenant JWKS and maps `oid`/`tid`/`groups`/`roles` (members of `ENTRA_ADMIN_GROUP` become admins); `both` accepts either.
* **Kill switch.** `ACL_ENFORCEMENT=false` disables filtering for single-user deployments.

## 4b. Structured data (`data.query`)

Questions that look measurable (revenue, counts, top-N, periods) route to `DATA`; those that also ask "why" or mention documents route to `HYBRID` (both tools run in parallel). The data step: verified-query match → else relevant tables (lexical overlap with names, columns, entity synonyms, plus FK neighbours) → compact schema context + approved semantics + verified examples → fast-model SQL as JSON → `SqlPolicy.validate` (single SELECT/UNION, nested writes and forbidden functions rejected, table allowlist, PII column denylist including projected `*`, join/subquery caps, LIMIT clamp) → execution with timeout and row cap (`LIMIT n+1` probe marks truncation) → `QueryResult`. Results become `[sql]` evidence the synthesizer must cite as measured facts, plus `table` and `chart` blocks (declarative spec, validated) streamed to the UI. Admins manage connections and the semantic model (`/data/connections`, `.../semantic`, `.../semantic/suggest`); every query is logged.

## 4c. Retrieval tiers

* **Relevance gate (CRAG-style).** After reranking, if the best score is below `RELEVANCE_GATE_THRESHOLD`, the fast model rewrites the query once in document phrasing; the retry is fused (RRF) with the first attempt and the trace records `adaptive_*` fields.
* **Document outline chunk.** Ingestion prepends one extractive overview chunk per document (title, section headings, table count, opening text; `chunk_level=document_summary`). Aggregation/analytical questions add a dedicated prefetch of those chunks so overview answers see every document.

## 4d. Observability

`core/telemetry.py` emits spans `bodham.answer` → `bodham.route` / `bodham.retrieve` / `bodham.synthesize` with GenAI-style attributes (operation name, model, token usage, intent, confidence, chunk ids, rerank scores, tool calls). Export is OTLP grpc (collectors) or OTLP http with headers (`OTLP_PROTOCOL=http`, `OTLP_HEADERS=Authorization=Basic ...` for Langfuse). Per-query traces are also persisted in the `traces` table.

## 5. Running modes

| Mode | Settings | External services |
|---|---|---|
| Tests | `APP_ENV=test` (set by `backend/conftest.py`) | none (SQLite, in-memory Qdrant, fake models) |
| Local, zero infra | `make dev-local` | NVIDIA API key only (SQLite, on-disk Qdrant, inline ingestion) |
| Docker | `make init` | PostgreSQL, Qdrant 1.19, Redis, worker; `--profile graph` adds Neo4j, `--profile storage` adds MinIO |
| Foundry IQ | `KNOWLEDGE_BACKEND=foundry_iq` + `AZURE_SEARCH_*`, `FOUNDRY_IQ_*` | Azure AI Search knowledge base (ingestion stays Azure-side) |

## 6. Roadmap

**v1:** retrieval engine, adapters, API, UI, eval harness.

**v2 (this branch):** MCP server + generic MCP adapter, permission model (ACL principals, mandatory filters, sharing, admin user management), Entra ID token validation, product renamed to Bodham. 217 tests.

**v3 (this branch):** connectors with ACL sync, the structured-data gateway, retrieval tiers, OTel export, table/chart blocks in the UI. 260 tests.

**v4 (next):**
3. Connectors: SharePoint/OneDrive, Google Drive, Confluence, S3/Blob, web crawl (Onyx-style connector ABC + scheduler).
4. Structured data tool (`data.query`): semantic model, NL→SQL, `sqlglot` AST policy (read-only, allowlists, limits), evidence type `sql` — the Bodham blueprint.
5. Retrieval tiers behind the router: CRAG-style relevance gating + iterative retrieval, RAPTOR-lite summaries for "summarise the whole document", LightRAG/HippoRAG graph tier for multi-hop, ColPali page retrieval for visual PDFs.
6. Observability: OTel GenAI spans → Langfuse/Phoenix; online RAGAS faithfulness sampling; cost per query by backend.
7. Product surface: notebooks/collections, source summaries, suggested follow-ups, report export, evidence drawer with highlight-to-source.
