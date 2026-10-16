# Market Research: Retrieval / RAG Platforms (October 2026)

This is the executive summary of three detailed reports in [`docs/research/`](research/):

| Report | Covers |
|---|---|
| [managed_platforms.md](research/managed_platforms.md) | Microsoft Foundry IQ / Azure AI Search agentic retrieval, Amazon Bedrock Knowledge Bases, Google Vertex AI RAG Engine + Agent Search, OpenAI file_search / Vector Stores, NVIDIA NeMo Retriever + RAG Blueprint, Cohere, Voyage, Jina, Mixedbread, Vectara, Pinecone Assistant, Ragie, Contextual AI, Glean, Anthropic |
| [opensource_frameworks_and_techniques.md](research/opensource_frameworks_and_techniques.md) | LlamaIndex, LangChain/LangGraph, Haystack, DSPy, RAGFlow, Dify, R2R, Morphik, Onyx, GraphRAG/LightRAG/HippoRAG, NVIDIA RAG Blueprint; hybrid search, late interaction, chunking, query transforms, reranking, embeddings, parsing, evaluation, Qdrant features |
| [interop_memory_governance.md](research/interop_memory_governance.md) | MCP / A2A, agent memory (Mem0, Graphiti, Letta), permission-aware retrieval, connectors, observability (OTel GenAI, Langfuse, Phoenix), guardrails, NotebookLM-style features, NVIDIA NIM model IDs and deprecations |

Every claim in those files is cited inline; items that could not be verified against a primary source from the sandbox are flagged `[search-only]` / `[unverified]`.

## 1. What the market converged on

1. **One retrieval contract.** Every platform, managed or open, reduces to `retrieve(query, filters, top_k) -> [{text, score, uri/doc_id, page/span, metadata}] + trace`. Managed platforms (Foundry IQ at `low`/`medium`, Bedrock agentic retrieval, Mixedbread, NVIDIA Blueprint) also *plan* queries themselves, so a client needs a "backend plans itself" capability flag to avoid double planning. This is exactly the `KnowledgeAdapter` boundary in this repo.
2. **MCP is the universal agent transport.** Foundry IQ exposes each knowledge base as an MCP server with a single `knowledge_base_retrieve` tool; Bedrock (via AgentCore Gateway), Pinecone, Ragie, Mixedbread, Glean, Qdrant and NVIDIA do the same. Current spec is 2026-07-28 (stateless Streamable HTTP). A2A is irrelevant for a knowledge source.
3. **The "strong pipeline" is the same everywhere:** structure-aware parsing → heading-aware chunks with contextual headers → hybrid dense + lexical fused by RRF → cross-encoder rerank → single grounded generation with validated citations → eval harness. Graph RAG, late interaction (ColPali) and iterative/agentic loops are optional tiers behind a router.
4. **Best-evidenced cheap wins:** contextual chunk headers + contextual BM25 + reranking cut top-20 retrieval failures from 5.7% to 1.9% (Anthropic); reranking is the single biggest lever (bge-reranker-v2-m3 / Qwen3-Reranker, NVIDIA `llama-nemotron-rerank-1b-v2`); multi-query fusion gains are largely neutralised after rerank+truncation, so it belongs behind a complexity router.
5. **Permission-aware retrieval is table stakes.** Glean, Azure AI Search (Entra ACLs, `x-ms-query-source-authorization`), Bedrock Managed KB (`userContext`), Onyx and Qdrant (payload partitioning, `is_tenant`) converge on: verified identity → ACL principals on every chunk → mandatory filter injected in the single retriever path → fail closed.
6. **Evaluation is a product feature:** RAGAS 0.4 (faithfulness is reference-free, usable online), DeepEval in CI, Langfuse (MIT core, OTLP) or Phoenix for traces, BEIR/BRIGHT/FRAMES/ViDoRe for benchmarks. Minimum harness: 150–300 gold questions with gold chunk ids, Recall@k / MRR per stage, LLM-judged faithfulness + relevancy, per-stage latency, CI thresholds.

## 2. Microsoft Foundry IQ in one page

* **What it is:** the product name for Azure AI Search *knowledge bases*: up to 10 *knowledge sources* (search index, Blob, OneLake, SharePoint indexed or remote via Copilot Retrieval API, Web via Bing, MCP servers) plus an Azure OpenAI deployment for planning/synthesis.
* **API:** `POST {endpoint}/knowledgebases('{kb}')/retrieve?api-version=2026-08-01-preview` with `messages[]`, `retrievalReasoningEffort {minimal|low|medium}`, `outputMode extractiveData|answerSynthesis`, `includeActivity/includeReferences`, `knowledgeSourceParams[].filterAddOn`, `maxRuntimeInSeconds`. Response: `response[]` (extractive JSON array or synthesized answer), `activity[]` (query planning, per-source searches with token counts), `references[]` (`docKey`, `rerankerScore`, `sourceData`). GA REST `2026-04-01` only covers `minimal` + extractive.
* **MCP:** `/knowledgebases/{kb}/mcp` exposes `knowledge_base_retrieve` (Entra bearer).
* **ACLs:** indexed SharePoint/ADLS sources are trimmed per user when the caller's token is forwarded in `x-ms-query-source-authorization`.
* **Billing:** Azure AI Search *retrieval tokens* (50M free/month) + Azure OpenAI tokens; Microsoft's worked example ≈ $4.32 per 2,000 retrievals (the Bodham cost model uses $0.00216/retrieval as the planning benchmark).
* **Does not:** bring-your-own embeddings/rerankers, GraphRAG, structured SQL, custom crawlers; needs Basic+ tier.
* **How we plug it in:** `FoundryIQAdapter` (`backend/src/knowledge/foundry_iq_adapter.py`) sends `outputMode=extractiveData` so the engine still synthesises once with its own validated citations, maps `references[]` to the shared chunk schema, keeps `activity[]` as the trace, forwards tenant/document filters as OData `filterAddOn`, and passes the user token for ACL trimming. Set `KNOWLEDGE_BACKEND=foundry_iq` and the three `AZURE_SEARCH_*` / `FOUNDRY_IQ_*` variables.

## 3. Other backends worth an adapter (priority order)

| Backend | Why | Effort |
|---|---|---|
| Any MCP knowledge server (Foundry IQ MCP, Qdrant MCP, Pinecone Assistant, Ragie, Mixedbread, Glean) | one generic `McpRetriever` adapter covers many vendors | small (needs `mcp` SDK ≥ 2.3) |
| Amazon Bedrock Knowledge Bases | `Retrieve` / `AgenticRetrieveStream`, managed ACLs, GraphRAG via Neptune | small (boto3) |
| OpenAI Vector Stores `/search` | model-agnostic hybrid search with attribute filters | small |
| Vertex AI RAG Engine `retrieveContexts` | corpus model, LLM ranker | small |
| NVIDIA RAG Blueprint `/v1/search` | same NIM stack as this repo, OpenAI-compatible | small |

## 4. NVIDIA NIM model notes (affects defaults in `.env.example`)

* Embedding: `nvidia/llama-nemotron-embed-1b-v2` (2048-d, Matryoshka 384–2048, 8k context) replaces `llama-3.2-nv-embedqa-1b-v2`; newer `nemotron-3-embed` (1B/8B) exists.
* Reranking: `nvidia/llama-nemotron-rerank-1b-v2` at `https://ai.api.nvidia.com/v1/retrieval/nvidia/llama-nemotron-rerank-1b-v2/reranking`; `llama-3.2-nv-rerankqa-1b-v2` and `rerank-qa-mistral-4b` are deprecated in 2026.
* Chat: `nvidia/nemotron-3-super-120b-a12b` (primary), `nvidia/nemotron-3-nano-30b-a3b` (routing/planning). Several 2025 IDs (`llama-3.3-70b`, `llama-4-maverick`, `deepseek-r1`) return 404/410 — the LLM client has a configurable fallback chain for this reason.
* Hosted free tier is community-reported at ~40 requests/minute per key; plan retries and caching accordingly.
* **Verify every model ID on build.nvidia.com before a demo**; the catalogue moves faster than docs.

## 5. What this means for Bodham

Implemented in this iteration (see [ARCHITECTURE_V3.md](ARCHITECTURE_V3.md)): the retrieval contract and adapter registry (local / Foundry IQ / mock), hybrid dense + BM25 sparse search with RRF in Qdrant, contextual chunk headers, NIM reranking with fallback, deterministic-first routing with bounded LLM planning, single synthesis with validated inline citations, per-query traces, an eval harness, and typed SSE events (`progress`, `evidence`, `answer_delta`, `done`).

Deferred (v2, in priority order): MCP server exposing `knowledge_retrieve`; ACL principals on chunks with mandatory filter injection from the verified identity; connectors (SharePoint, Google Drive, Confluence, S3); Langfuse/OTel export of traces; a structured-data (`data.query`) tool with AST-validated read-only SQL as in the Bodham blueprint; CRAG-style multi-hop loop and HippoRAG/LightRAG graph tier behind the router; Docling as the default PDF parser in the Docker image; NotebookLM-style notebooks, summaries and follow-ups.
