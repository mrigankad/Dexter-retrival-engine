# BUILD_STATUS

_Last updated: 2026-10-16 (branch `claude/gallant-lovelace-lujn7r`)_

## Phase 2 (this commit)

| Area | What |
|---|---|
| Rename | Product is **Bodham** everywhere (settings, prompts, compose names, UI, docs); the GitHub repository slug is unchanged. |
| MCP server | `src/mcp_server/` mounted at `/mcp` (streamable HTTP, stateless, JSON). Tools: `knowledge_retrieve`, `list_documents`, `list_backends`. Bearer auth: Bodham JWT, Entra token or `MCP_API_TOKEN`; identity drives ACL filters. A fresh server is created per host lifespan (SDK session manager is single-use). |
| MCP adapter | `KNOWLEDGE_BACKEND=mcp` → `McpKnowledgeAdapter` calls `MCP_TOOL_NAME` on `MCP_SERVER_URL` with `MCP_AUTH_TOKEN`; parses structured content / JSON / text; works against Foundry IQ (`knowledge_base_retrieve`) or another Bodham. |
| Permission model | Principals (`public`, `tenant:`, `user:`, `group:`) stored as `acl` on every chunk; `RetrievalFilters.principals` enforced in Qdrant and the mock adapter; filters derived from the verified token in chat, `/knowledge/retrieve` and MCP; documents carry `visibility` + `shared_groups`; `PUT /documents/{id}/sharing` re-indexes; owner/admin checks on delete, reprocess, sharing; anonymous → public only; `ACL_ENFORCEMENT` kill switch. |
| Auth | JWTs carry `tenant_id`, `role`, `groups`; `GET /auth/users`, `PUT /auth/users/{username}` (admin); `AUTH_MODE=local|entra|both` with Entra ID JWKS validation (`src/core/auth.py`); lightweight column migration on startup for existing databases. |
| Tests | 217 passing: MCP tools in-process, MCP over the real streamable-HTTP client via ASGI, auth rejection, MCP adapter + engine on top of MCP, ACL visibility/groups/admin/anonymous through the HTTP API, Entra token validation with a generated RSA key, access helpers. |

## Phase 1 (previous commit)

Research (`docs/MARKET_RESEARCH.md`, `docs/research/`), contracts, infrastructure (PostgreSQL/SQLite, Qdrant hybrid), NIM clients, ingestion, hybrid retrieval, orchestrator, API, eval harness, frontend events, packaging.

## Commands

```bash
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && python -m pytest -q
make dev-local                      # SQLite + embedded Qdrant + inline ingestion; needs NVIDIA_API_KEY
cp .env.example .env && make init   # full Docker stack
make eval DATASET=evals/datasets/sample.json
# MCP: POST http://localhost:8000/mcp  with  Authorization: Bearer <MCP_API_TOKEN or user token>
```

## Decisions

* MCP auth is bearer-token based for now; OAuth 2.1 metadata/discovery is deferred.
* The MCP service token is tenant-scoped (sees everything the deployment's tenant holds); per-user access requires the user's own token.
* Entra identities are not materialised as `users` rows; their claims drive access directly. Document ownership for Entra users is recorded in `doc_metadata.owner`.

## Not done / next

1. Connectors (SharePoint/OneDrive, Google Drive, Confluence, S3, web) with ACL sync.
2. Structured-data tool (`data.query`) with AST-validated read-only SQL and a semantic model (Bodham blueprint §10–11).
3. Retrieval tiers behind the router (CRAG loop, RAPTOR-lite, graph tier), OTel/Langfuse export, notebooks/summaries/follow-ups.
4. Live validation against NVIDIA NIM, Azure AI Search and Entra ID with real credentials.
