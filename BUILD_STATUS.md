# BUILD_STATUS

_Last updated: 2026-10-16 (branch `claude/gallant-lovelace-lujn7r`)_

## Phase 3 (latest commits)

| Area | What |
|---|---|
| Connectors | `src/connectors/`: local folder, web/sitemap, S3, SharePoint/OneDrive (Graph delta + permissions), Google Drive (permissions, Docs export), Confluence (restrictions). Sync service with change detection, removal, ACL from source (`visibility=source`), delta cursors, run history; scheduler; admin API `/connectors`. |
| Structured data | `src/data_gateway/`: read-only connections, discovery, semantic model (entities/metrics/synonyms/verified queries), NL→SQL with policy feedback, sqlglot AST policy, capped execution, charts. `DATA`/`HYBRID` intents; `[sql]` evidence; `table`/`chart` SSE blocks; API `/data/*`. |
| Retrieval tiers | CRAG-style relevance gate with one query rewrite; extractive document-outline chunk used for overview questions. |
| Telemetry | OTel spans per stage with GenAI attributes; OTLP grpc or http (Langfuse headers) exporter. |
| Frontend | Renders table and chart blocks (inline SVG line/bar/kpi following the data-viz method: thin rounded bars, 2px lines, hover crosshair, legend for multi-series, table view always present). |
| Tests | 260 passing: connector mapping + lifecycle + mock transports, SQL policy matrix, semantic ranking, query service retry/clarification, engine DATA/HYBRID, data API, summary chunks, relevance gate, OTel spans, exporter factory. |

## Phase 2

Rename to Bodham; MCP server (`/mcp`) and generic MCP adapter; permission model (ACL principals, mandatory filters, sharing, admin users); Entra ID validation.

## Phase 1

Research, contracts, infrastructure (PostgreSQL/SQLite, Qdrant hybrid), NIM clients, ingestion, hybrid retrieval, orchestrator, API, eval harness, frontend events, packaging.

## Commands

```bash
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && python -m pytest -q
make dev-local                      # SQLite + embedded Qdrant + inline ingestion; needs NVIDIA_API_KEY
cp .env.example .env && make init   # full Docker stack
make eval DATASET=evals/datasets/sample.json
# connectors:  POST /connectors {"type":"sharepoint","name":"Policies","settings":{"tenant_id":..,"client_id":..,"client_secret":"env:SP_CLIENT_SECRET","drive_id":..},"visibility":"source"}
# data:        POST /data/connections {"id":"sales","name":"SalesDB","dialect":"postgres","url":"env:SALES_DB_URL"} then POST /data/query {"question":"revenue by month"}
```

## Decisions

* Connector secrets are stored as `env:VAR` references, never plaintext; the API masks secret-looking settings.
* `visibility=source` fails closed: an item with no readable principals is visible to admins only.
* No LLM output reaches a database without `SqlPolicy`; raw SQL (admins) goes through the same policy.
* Entra object ids are the user principals for SharePoint ACLs, so per-user trimming of Graph-synced content requires `AUTH_MODE=entra`.
* The relevance gate costs one fast-model call only when the reranker's best score is weak.

## Not done / next

1. Graph tier (LightRAG/HippoRAG-style) and ColPali page retrieval behind the router.
2. Notebooks/collections, source summaries, suggested follow-ups, report export.
3. OAuth 2.1 on the MCP server; service-account flows for Google Drive; incremental Confluence sync.
4. Live validation against NVIDIA NIM, Azure AI Search, Entra ID, Microsoft Graph and a real PostgreSQL warehouse.
