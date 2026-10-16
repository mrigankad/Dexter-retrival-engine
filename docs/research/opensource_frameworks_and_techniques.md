# Open-source retrieval / RAG: state of the art (research snapshot, 2026-10-16)

Purpose: inform the design of a self-hosted retrieval engine (Python + FastAPI + Qdrant + NVIDIA NIM for LLM/embeddings) that must beat a naive "embed → top-k → stuff into prompt" pipeline.

Method: web search (extended mode for anything that may have moved in the last 12 months) plus direct reads of official docs, GitHub READMEs / release pages and papers. GitHub star counts and licenses were pulled from the GitHub API on 2026-10-16. Where a number comes only from a secondary source it is flagged "(secondary)". Several official doc hosts (qdrant.tech, docs.ragas.io, huggingface.co, arxiv.org, microsoft.github.io) could not be fetched directly from this sandbox; in those cases I used the GitHub-hosted source of the same docs (e.g. `qdrant/landing_page`, `microsoft/graphrag/docs`) or search-result excerpts, and I say so.

---

## 0. TL;DR

1. The field has converged on a standard "good" pipeline: structure-aware parsing → structure-aware chunking with contextual headers → hybrid (dense + lexical/sparse) retrieval fused with RRF → cross-encoder reranking → grounded generation with citations → an eval harness. Every strong framework (RAGFlow, NVIDIA RAG Blueprint, Dify, Open WebUI, Onyx, LightRAG, ragbits) ships exactly this. Graph-RAG and late-interaction are optional layers for specific query classes.
2. Qdrant 1.19.x (Aug–Oct 2026) natively supports all of it: Query API with `prefetch` + `rrf` (configurable `k` since 1.16, weighted RRF since 1.17) / `dbsf`, sparse vectors with IDF (per-query IDF scoping since 1.19), multivectors with `max_sim`, binary/scalar/4-bit TurboQuant quantization, full-text payload index (stemming, stopwords, phrase, ASCII folding), tiered multitenancy (1.16), strict mode (1.13+), formula/score-boosting queries (1.14+). ([Qdrant releases](https://github.com/qdrant/qdrant/releases), [hybrid-queries doc source](https://github.com/qdrant/landing_page/blob/master/qdrant-landing/content/documentation/search/hybrid-queries.md))
3. Best-evidenced cheap wins: (a) hybrid + contextual chunk headers + reranking cut Anthropic's top-20 retrieval failure rate from 5.7% to 1.9% (−67%) ([Anthropic](https://www.anthropic.com/news/contextual-retrieval)); (b) reranking is the single highest-leverage stage (Qwen3-Reranker-8B 68.97, bge-reranker-v2-m3 67.64 BEIR nDCG@10 in [Querit, arXiv 2606.19037](https://arxiv.org/pdf/2606.19037)); (c) structure-aware chunking (Docling HybridChunker, parent/child) beats semantic chunking, whose extra cost is not justified by consistent gains ([Qu et al., NAACL Findings 2025](https://arxiv.org/html/2410.13070v1)).
4. GraphRAG helps on multi-hop / relational questions (HippoRAG 2 53.4% vs reranked RAG 42.9% on GraphRAG-Bench complex reasoning) but loses to reranked vector RAG on fact lookup and summarization (60.9 vs 49.3) and costs 10–100× more to index ([GraphRAG-Bench, arXiv 2506.05690](https://www.alphaxiv.org/abs/2506.05690)). Treat it as a v2 feature behind a router, with HippoRAG 2 or LightRAG, not Microsoft GraphRAG, as the implementation.
5. For a self-hosted PDF/DOCX/PPTX/XLSX parser the pragmatic default is Docling (MIT, v2.140.0, 69k stars, native Office formats, HybridChunker, VLM pipeline), with MinerU (GPU, best on scanned/CJK/formula-heavy) or NVIDIA nv-ingest (if you already run NIMs) as upgrade paths; Marker's weights are not free for commercial use above $5M revenue.
6. Three reference architectures worth borrowing from: NVIDIA RAG Blueprint (closest to your stack: NIM embed/rerank/LLM, hybrid, query decomposition, reflection, citations, RAGAS eval), RAGFlow (DeepDoc parsing, template chunking, multi-recall + fused rerank, agentic retrieval, 92k stars, Apache-2.0), and LightRAG/HippoRAG 2 as the graph layer design. LlamaIndex remains the best component library to copy patterns from (parent/child, auto-merging, RAPTOR pack, StructuredLLMRerank).

---

## Part A — Frameworks and open-source RAG products

Star counts and licenses: GitHub API, 2026-10-16. "Last push" = last commit date on the default branch.

| Project | Stars | License | Last push | Status / one-liner |
|---|---|---|---|---|
| langgenius/dify | 158.6k | Apache-2.0 + Dify conditions | 2026-10-16 | Low-code agent/RAG platform; Knowledge Pipeline |
| open-webui/open-webui | 155.9k | Open WebUI License (BSD-3 derived, branding clause) | 2026-10-16 | Chat UI with knowledge bases |
| langchain-ai/langchain | 147.9k | MIT | 2026-10-16 | langchain 1.4.6 / langchain-core 1.6.11 |
| infiniflow/ragflow | 92.3k | Apache-2.0 | 2026-10-16 | 1.0.0-rc1/rc2 (Go rewrite), DeepDoc |
| docling-project/docling | 69.0k | MIT | 2026-10-16 | v2.140.0 parser |
| Mintplex-Labs/anything-llm | 67.2k | MIT | 2026-10-16 | Desktop/self-hosted RAG app |
| run-llama/llama_index | 52.5k | MIT | 2026-10-14 | v0.14.25 |
| langchain-ai/langgraph | 43.4k | MIT | 2026-10-16 | 1.x runtime |
| HKUDS/LightRAG | 40.2k | MIT | 2026-10-15 | Graph+vector RAG, EMNLP 2025 |
| stanfordnlp/dspy | 38.7k | MIT | 2026-10-16 | 3.4.1 |
| microsoft/graphrag | 36.4k | MIT | 2026-10-12 | v3.3.0 |
| onyx-dot-app/onyx | 32.5k | MIT (CE) + Enterprise license for `ee/` | 2026-10-16 | Enterprise search; Zoom acquisition reported Sept 2026 (secondary) |
| deepset-ai/haystack | 26.7k | Apache-2.0 | 2026-10-16 | v3.4.0 |
| Cinnamon/kotaemon | 25.8k | Apache-2.0 | 2026-07-14 | Slowed; last release v0.12.0 |
| neuml/txtai | 13.0k | Apache-2.0 | 2026-10-16 | v9.13.0 |
| SciPhi-AI/R2R | 8.0k | MIT | 2025-11-07 | Stale for ~11 months |
| weaviate/Verba | 7.7k | BSD-3 | archived 2026-06-08 | Discontinued |
| truefoundry/cognita | 4.4k | Apache-2.0 | archived 2026-03-13 | Discontinued |
| OSU-NLP-Group/HippoRAG | 4.1k | MIT | 2026-10-06 | HippoRAG 2 (ICML 2025), 2.0.0a5 |
| gusye1234/nano-graphrag | 4.0k | MIT | 2026-01-27 | Minimal GraphRAG; low activity |
| morphik-org/morphik-core | 3.7k | BSL 1.1 (source-available) | 2026-10-14 | Multimodal/ColPali RAG |
| microsoft/kernel-memory | 2.2k | MIT | 2026-06-08 | C# research project; issues/PRs disabled |
| deepsense-ai/ragbits | 1.7k | MIT | 2026-05-18 | Modular Python toolkit, Qdrant + Docling |
| NVIDIA-AI-Blueprints/rag | 0.8k | Apache-2.0 (code); NVIDIA model licenses | 2026-09-03 | Reference RAG on NIMs, v2.6.0 |
| BUPT-GAMMA/PathRAG | 0.4k | none declared | 2025-12-17 | Research code |

### A.1 LlamaIndex (+ LlamaCloud → "LlamaParse" platform, LlamaParse / LlamaExtract)
- What: the broadest Python component library for RAG — node parsers (sentence-window, hierarchical/auto-merging, semantic splitter), retrievers (hybrid, recursive, auto-merging, router), postprocessors/rerankers (`LLMRerank`, `StructuredLLMRerank`, cross-encoder, Cohere/NVIDIA integrations), property-graph index, RAPTOR llama-pack, Workflows for agentic orchestration. Latest framework release v0.14.25 (2026-09-21); 0.14.24 added async `LLMRerank`, multimodal query engines landed in 0.14.23. ([releases](https://github.com/run-llama/llama_index/releases))
- Commercial side: in Feb 2026 LlamaCloud was re-branded "LlamaParse" as the enterprise document-processing platform; Parse API v2 and new SDKs (Python/TS parity) shipped Jan 2026; LiteParse is a newer local parsing option; a document-extraction leaderboard with Kaggle was announced ([newsletter 2026-02-24](https://www.llamaindex.ai/blog/llamaindex-newsletter-2026-02-24), [Parse API v2](https://www.llamaindex.ai/blog/announcing-new-llamacloud-sdks-and-parse-api-v2), [blog](https://www.llamaindex.ai/blog)). LlamaParse pricing is credit-based (Fast 1 credit/page, Agentic Plus 45 credits/page; ~10k free credits/month) (secondary: [apiscout](https://apiscout.dev/guides/llamaparse-vs-reducto-best-document-ai-api-2026)).
- Notable: the richest set of ready-made retrieval patterns to copy; MIT; 52.5k stars. Weakness: abstractions churn and the library is heavy; use as a pattern catalogue rather than a runtime dependency.

### A.2 LangChain + LangGraph
- LangChain 1.0 and LangGraph 1.0 shipped Oct 22, 2025; legacy chains moved to `langchain-classic`. Current: langchain 1.4.6 (2026-10-14), langchain-core 1.6.11 (2026-10-15); LangGraph supplies durable execution, HITL, streaming; `create_agent` + middleware (PII, summarization, HITL) is the agent abstraction. ([langchain 1.0 blog](https://www.langchain.com/blog/langchain-langgraph-1dot0), [middleware](https://www.langchain.com/blog/agent-middleware), [releases](https://github.com/langchain-ai/langchain/releases))
- Retrieval-wise it is a thin integration layer (Qdrant vector store, `MultiQueryRetriever`, `ParentDocumentRetriever`, `EnsembleRetriever`, contextual compression). The useful part for us is LangGraph as a state machine for agentic/corrective RAG loops (the canonical CRAG / Self-RAG / Adaptive-RAG tutorials are LangGraph graphs). MIT.

### A.3 Haystack (deepset)
- Haystack 3.0.0 (2026-07-20) was a major release centred on production agents: hooks (`before_llm`, `before_tool` …), `SkillToolset`, unified `Pipeline` with `run_async`/`stream()`, tool-result offloading, trusted-module allowlist for deserialization, mocks for testing; several integrations moved to separate packages. 3.1–3.4 added `CompactionHook`, `AgentTool`, `SummarizationCompactor`, `TokenBudgetHook`, faster `SentenceWindowRetriever`; v3.4.0 (2026-10-15) requires Python ≥3.11. Hayhooks 2.0 (Oct 2026) deploys pipelines as REST/MCP with durable (Redis-checkpointed) execution. ([3.0.0 notes](https://github.com/deepset-ai/haystack/releases/tag/v3.0.0), [releases](https://github.com/deepset-ai/haystack/releases), [hayhooks](https://github.com/deepset-ai/hayhooks/releases/tag/v2.0.0))
- Notable: explicit DAG pipelines, strong typing, Qdrant document store with hybrid support, NVIDIA NIM integrations. Apache-2.0, 26.7k stars. Heavier than we need but its component contracts (DocumentSplitter → Embedder → Writer; Retriever → Ranker → Builder → Generator) are a clean model for our own module boundaries.

### A.4 DSPy
- 3.0 (2025) introduced GEPA (reflective prompt evolution), SIMBA, GRPO; 3.2 added BetterTogether optimizer chaining; 3.4.x (3.4.1 on 2026-10-12) made the structured `InstructionProposer` GEPA's default, added `ReActV2`, `RLM` sub-agents, `LocalInterpreter`. ([3.0.0](https://github.com/stanfordnlp/dspy/releases/tag/3.0.0), [releases](https://github.com/stanfordnlp/dspy/releases), [GEPA paper](https://arxiv.org/pdf/2507.19457))
- Relevance: not a RAG framework, but the right tool to *optimise* our query-rewriting, routing and answer-synthesis prompts against our eval set once the harness exists (MIPROv2/GEPA on a `dspy.Module` that wraps our retriever). MIT, 38.7k stars.

### A.5 RAGFlow (InfiniFlow)
- Full RAG engine with a UI: DeepDoc (layout analysis, OCR, table recognition — CPU inference in 1.0), template-based explainable chunking, "multiple recall paired with fused re-ranking", grounded citations, agentic retrieval (Low/Medium/High/Ultra thinking modes), Knowledge Compilation (v0.27, Aug 2026: wikis, graphs, trees, PageIndex, mind maps, timelines), SoMark layout-aware OCR (0.26.3). Document engine: Elasticsearch or Infinity. 1.0.0-rc1 (2026-09-29) is a comprehensive rewrite in Go; rc2 tag exists. Apache-2.0, 92.3k stars. ([README](https://github.com/infiniflow/ragflow), [release notes](https://github.com/infiniflow/ragflow/blob/main/docs/release_notes.md))
- Notable: the most complete open reference for "enterprise document QA with citations"; parsing-first philosophy. Weakness: monolith, moving to Go, not Qdrant-native.

### A.6 Dify
- Low-code LLM app platform. Knowledge Pipeline (visual RAG ETL), three chunk modes (General, Parent-Child, Q&A); "Parent-child-HQ" template = parent/child + high-quality indexing + hybrid search; parent-child retrieval arrived in v0.15. License is Apache-2.0 with added conditions: no multi-tenant operation without written permission and no removal of console logo/copyright (OSI list discussion questions whether this is open source). 158.6k stars. ([Knowledge Pipeline](https://dify.ai/blog/introducing-knowledge-pipeline), [chunk docs](https://docs.dify.ai/en/cloud/use-dify/knowledge/create-knowledge/chunking-and-cleaning-text), [license-discuss](https://lists.opensource.org/pipermail/license-discuss_lists.opensource.org/2025-October/022428.html))

### A.7 R2R (SciPhi)
- "Agentic RAG with a RESTful API": hybrid search, automatic entity/relationship extraction into knowledge graphs, Deep Research API (multi-step reasoning over KB + web). Postgres(+pgvector) based. MIT, 8.0k stars, but last push 2025-11-07 — effectively unmaintained; do not depend on it, but its REST surface (documents / collections / chunks / search / rag / agent) is a good API design to mirror. ([README](https://github.com/SciPhi-AI/r2r))

### A.8 Morphik
- Multimodal retrieval engine built around ColPali-style visual embeddings, plus KG and cache-augmented generation. **Not open source**: Business Source License 1.1 (free for personal/indie use and for commercial deployments under US$2k/month revenue; converts to Apache-2.0 four years after each release). 3.7k stars. ([README](https://github.com/morphik-org/morphik-core))

### A.9 Kotaemon (Cinnamon)
- Gradio RAG UI with hybrid retrieval, GraphRAG/LightRAG/nano-graphrag integration, citation viewer. Latest release v0.12.0 (31 May; sources disagree on year), last push 2026-07-14, >200 open issues — treat as dormant. Apache-2.0, 25.8k stars. ([releases](https://github.com/Cinnamon/kotaemon/releases))

### A.10 Cognita (TrueFoundry) — archived 2026-03-13 (read-only). Modular RAG with built-in frontend; Apache-2.0; 4.4k stars. Not a candidate. ([repo](https://github.com/truefoundry/cognita))

### A.11 txtai (NeuML)
- All-in-one embeddings database (SQLite/Postgres + Faiss/HNSW + graph) with RAG pipelines and agents. Very active: v9.13.0 (~Aug 2026) added LEMUR learned multi-vector retrieval, expanded late-interaction, MUVERA; v9.11 added LiteParse extraction; v9.9 zero-dependency install + Transformers v5. Apache-2.0, 13.0k stars. Good source of ideas for late-interaction indexing on a budget, but not Qdrant-based. ([releases](https://github.com/neuml/txtai/releases))

### A.12 Onyx (ex-Danswer)
- Enterprise search/assistant with 40+ connectors, permission-aware search, hybrid retrieval. v4.0 (May 2026) replaced Vespa with OpenSearch; weekly releases (v4.8.0 Sept 2026, secondary). Community Edition MIT; `ee/` directories under a commercial Onyx Enterprise License (SSO, per-user permission sync are EE). Zoom acquisition reported 2026-09-23 (secondary only). 32.5k stars. ([comparison](https://wz-it.com/en/blog/onyx-self-hosted-installation/), [repo](https://github.com/onyx-dot-app/onyx))

### A.13 Verba (Weaviate) — archived 2026-06-08; last release v2.1.2 (Jan). Not a candidate. ([releases](https://github.com/weaviate/Verba/releases))

### A.14 ragbits (deepsense.ai)
- Modular Python toolkit: `ragbits-core` (LiteLLM, typed prompts, Qdrant/pgvector stores), `ragbits-document-search` (ingestion via Docling or Unstructured, 20+ formats, VLM table/image extraction, S3/GCS/Azure, Ray distributed ingestion), `ragbits-agents` (A2A, MCP), `ragbits-evaluate`, `ragbits-guardrails`, `ragbits-chat` (UI + API + feedback). MIT, 1.7k stars, last push 2026-05-18. Closest in spirit (Python, Qdrant, Docling) to what we're building — worth reading its document-search package for structure. ([README](https://github.com/deepsense-ai/ragbits))

### A.15 Open WebUI knowledge
- Knowledge bases with hybrid (BM25 + vector) retrieval and cross-encoder reranking; "focused" (RAG) vs "full context" modes; newer opt-in agentic KB mode (`ENABLE_KB_EXEC`) gives the model a shell-like interface over KBs. License: since v0.6.6 (Apr 2025) the "Open WebUI License" (BSD-3 plus a branding clause for deployments >50 users/30 days unless licensed). v0.11.4 (Sept 2026, secondary). 155.9k stars. ([RAG docs](https://docs.openwebui.com/features/chat-conversations/rag/), [license](https://docs.openwebui.com/license/))

### A.16 AnythingLLM
- Desktop + Docker RAG app; workspace = KB, embed-or-attach documents, agents. MIT. v1.17.0 (2026-10-01, secondary). 67.2k stars. Consumer-grade retrieval (no reranker by default); a UI reference, not an engine reference. ([review](https://aifoss.dev/blog/anythingllm-review-2026/))

### A.17 Microsoft GraphRAG
- v3.3.0 (2026-10-08). Indexing: Standard (LLM entity/relationship extraction, claims, community reports; extraction ≈75% of indexing cost) or Fast (NLTK/spaCy noun-phrase entities, co-occurrence edges, LLM only for community reports). Query: Local (entities + text units), Global (map-reduce over community reports; resource-intensive), DRIFT (local seeded with community context, follow-up questions), Basic (plain vector RAG for comparison). LazyGraphRAG (claimed 0.1% of GraphRAG indexing cost) is still not in the OSS library as far as any primary source shows (discussion #1490). MIT, 36.4k stars. ([releases](https://github.com/microsoft/graphrag/releases), [query overview src](https://github.com/microsoft/graphrag/blob/main/docs/query/overview.md), [index methods src](https://github.com/microsoft/graphrag/blob/main/docs/index/methods.md), [LazyGraphRAG](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/), [discussion](https://github.com/microsoft/graphrag/discussions/1490))

### A.18 LightRAG (HKUDS)
- EMNLP 2025. Dual-level retrieval over an entity/relationship graph plus vector chunks; modes naive/local/global/hybrid/mix (default mix). Storage is pluggable: Postgres recommended for all four stores; **Qdrant supported as the vector store**; Neo4j/Memgraph for graphs. 2026 additions: RAG-Anything merged (multimodal parsing via MinerU or Docling), four chunking strategies, role-specific LLMs, reranking on by default (+1–2 s), REST server + WebUI. Paper win-rates vs NaiveRAG 60–85%, vs GraphRAG ~50–55% (authors' LLM-judge). Independent GraphRAG-Bench results are weaker (see B8). MIT, 40.2k stars. ([README](https://github.com/HKUDS/LightRAG))

### A.19 HippoRAG 2 (OSU)
- ICML 2025, arXiv 2502.14802. OpenIE triples + passage nodes in one graph, Personalized PageRank seeded from query entities/facts, dense retrieval for passages and facts. Claims +7% on associative-memory (multi-hop) tasks over NV-Embed-v2 with no regression on factual QA; much cheaper indexing than GraphRAG/RAPTOR/LightRAG. Version 2.0.0a5. MIT, 4.1k stars. ([README](https://github.com/OSU-NLP-Group/HippoRAG), [paper](https://arxiv.org/pdf/2502.14802))

### A.20 PathRAG — research code (BUPT), flow-based pruning of relational paths; no license file; stale since Dec 2025; no independent benchmark found. Skip. ([repo](https://github.com/BUPT-GAMMA/PathRAG))

### A.21 nano-graphrag — ~1k-line hackable GraphRAG (MIT, 4.0k stars, last push Jan 2026). Useful to read to understand GraphRAG's local/global mechanics; LightRAG was forked from it. ([repo](https://github.com/gusye1234/nano-graphrag))

### A.22 Microsoft kernel-memory — .NET "memory" service (ingest, partition, embed, hybrid search, citations); labelled research project, issues/PRs disabled, last push June 2026. Only relevant as a design reference for its pipeline-step model (extract → partition → embed → save). ([repo](https://github.com/microsoft/kernel-memory))

### A.23 NVIDIA RAG Blueprint
- v2.6.0 (NGC, June 2026). Components: LangChain-based RAG orchestrator server, ingestor server on NeMo Retriever Extraction (nv-ingest 26.x), vector DB (Elasticsearch default in current README, GPU Milvus alternative, cuVS-accelerated), S3-compatible object store, rag-frontend. NIMs: `llama-nemotron-embed-1b-v2` (+ `-vl` variant), `llama-nemotron-rerank-1b-v2` (+ `-vl`), LLM `nemotron-3-super-120b-a12b`, optional VLM (Nemotron Nano Omni 30B A3B), guardrails NIMs. Features: hybrid dense+sparse, reranking, multi-collection, query decomposition + dynamic filter generation, optional reflection (query rewrite + answer check), citations, multimodal ingestion (text/tables/charts/infographics/audio), plan-and-execute agentic RAG, RAGAS evaluation scripts, OpenAI-compatible API, Helm charts. Release 2.5.0 (Mar 2026) renamed the models from `llama-3.2-nv-embedqa-1b-v2` / `llama-3.2-nv-rerankqa-1b-v2` to the nemotron names. Code Apache-2.0; models under NVIDIA Open Model / Llama 3.2 Community licenses. ([README](https://github.com/NVIDIA-AI-Blueprints/rag), [2.5.0 release notes](https://docs.nvidia.com/rag/2.5.0/release-notes.html), [NGC](https://catalog.ngc.nvidia.com/orgs/nvidia/blueprint/helm-charts/nvidia-blueprint-rag/-))

### A.24 Which 3 reference architectures to borrow from, and why

1. **NVIDIA RAG Blueprint** — same model stack we will run (NIM embed/rerank/LLM); shows the exact stage order NVIDIA validated at scale (ingest → extraction NIMs → hybrid → rerank → optional reflection → cited answer), the config knobs worth exposing (query decomposition, filter generation, reflection on/off, multi-collection), and a RAGAS-based eval loop. Copy its request/response schema and stage layering; replace Milvus/Elasticsearch with Qdrant.
2. **RAGFlow** — the best open evidence that parsing quality dominates enterprise document QA: DeepDoc layout/OCR/table recognition, explainable chunk templates per document type, multi-recall + fused reranking, citations with traceable references, agentic retrieval modes. 92k stars and Apache-2.0 mean its UX (chunk preview, citation highlighting, chunk editing) is the de-facto user expectation. Copy its ingestion ergonomics and citation model.
3. **LightRAG / HippoRAG 2 (graph layer)** — for the optional multi-hop tier. LightRAG gives a production-shaped implementation with Qdrant as its vector store, pluggable graph DB, reranker-by-default and a REST server; HippoRAG 2 gives the cheapest-to-index graph design with the best independent multi-hop numbers. Borrow LightRAG's dual-level (entity + relation + chunk) retrieval contract and HippoRAG's passage-node + PPR idea rather than Microsoft GraphRAG's community-summary pipeline, whose indexing cost is an order of magnitude higher.

Honourable mentions: LlamaIndex (component patterns: hierarchical node parser + auto-merging retriever, RAPTOR pack, structured LLM rerank), ragbits (Python + Qdrant + Docling project layout), Haystack 3 (pipeline/component contracts and hooks).

---

## Part B — Retrieval techniques

### B1. Hybrid search (dense + lexical/sparse, fused)

**What.** Run a dense ANN query and a lexical/sparse query in parallel and fuse the two ranked lists. Reciprocal Rank Fusion: score(d) = Σ 1/(k + rank_i(d)). Qdrant uses zero-based ranks and default k = 2 (configurable since 1.16; the classic literature value is 60) ([hybrid-queries source](https://github.com/qdrant/landing_page/blob/master/qdrant-landing/content/documentation/search/hybrid-queries.md)). DBSF (distribution-based score fusion, 1.11+) z-normalises each list with mean ± 3σ and sums; use only if you trust raw score magnitudes.

**Measured gains.**
- Anthropic: contextual embeddings alone cut top-20 failure rate 5.7% → 3.7% (−35%); adding contextual BM25 → 2.9% (−49%); adding reranking → 1.9% (−67%) ([Anthropic](https://www.anthropic.com/news/contextual-retrieval)).
- Qdrant's own tests: the second retriever adds ~0.6–1.5 ms median latency on one container ([Qdrant hybrid-search article, via search](https://qdrant.tech/articles/hybrid-search/)).
- Caveat: a 2026 industry study found multi-query *fusion* gains in raw recall are "largely neutralised after re-ranking and truncation" ([arXiv 2603.02153](https://arxiv.org/abs/2603.02153v1)) — fuse dense+sparse, but don't expect stacking many fused lists to keep paying.

**Lexical options on Qdrant (all via fastembed, Apache-2.0, ONNX, CPU-friendly):**
- `Qdrant/bm25` — sparse BM25 vectors; Qdrant computes IDF server-side with `modifier: idf` (1.10+); v0.9.0 of fastembed added `stemmer` and `stopwords` options; per-query IDF corpus scoping (`idf` search param) since Qdrant 1.19 so multitenant IDF stats can be per tenant ([fastembed releases](https://github.com/qdrant/fastembed/releases), [indexing doc source](https://github.com/qdrant/landing_page/blob/master/qdrant-landing/content/documentation/manage-data/indexing.md)).
- `Qdrant/minicoil-v1` (fastembed ≥0.7.0) — BM25 formula with contextual term re-weighting (self-supervised; English); needs the IDF modifier ([miniCOIL article](https://qdrant.tech/articles/minicoil/)).
- SPLADE++ (`prithivida/Splade_PP_en_v1`) — learned sparse with term expansion; English only; heavier at query time.
- BGE-M3 sparse — multilingual learned sparse from the same model that gives dense + ColBERT vectors (MIT, 1024-d, 8192 tokens) ([bge-m3 card via NVIDIA](https://build.nvidia.com/baai/bge-m3/modelcard)). Qdrant's guidance: start with BM25, measure a learned sparse model against it before adopting.

**Implementation sketch (qdrant-client ≥1.16, illustrative):**
```python
from qdrant_client import QdrantClient, models
client.create_collection(
  "docs",
  vectors_config={"dense": models.VectorParams(size=2048, distance=models.Distance.COSINE,
                   on_disk=True)},
  sparse_vectors_config={"bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)},
  quantization_config=models.ScalarQuantization(scalar=models.ScalarQuantizationConfig(type=models.ScalarType.INT8, always_ram=True)),
)
res = client.query_points(
  "docs",
  prefetch=[
    models.Prefetch(query=dense_q, using="dense", limit=100, filter=tenant_filter),
    models.Prefetch(query=models.SparseVector(**bm25_q), using="bm25", limit=100, filter=tenant_filter),
  ],
  query=models.FusionQuery(fusion=models.Fusion.RRF),   # rrf k / weights are newer client fields
  limit=50, with_payload=True,
)
```
Weighted RRF (1.17): one weight per prefetch in order; tune on a train/validation split of your eval set, otherwise keep 1.0/1.0. Note that fusion inside a prefetch runs per shard; fusion as the *main* query merges globally.

### B2. Late interaction / multi-vector

**ColBERT v2** (arXiv 2112.01488): token-level embeddings, MaxSim scoring; residual compression reduces footprint 6–10× (abstract) and keeps BEIR ~50 nDCG@10 mean (secondary, [reproduction 2604.09982](https://arxiv.org/pdf/2604.09982)). fastembed ships `colbert-ir/colbertv2.0` and, since v0.9.0, LateOn / mLateOn (multilingual) late-interaction models; `answerdotai/answerai-colbert-small-v1` is the usual small choice.

**ColPali / ColQwen** (arXiv 2407.01449): embed page *images* with a VLM into ~1k patch vectors, MaxSim against query tokens; ColPali scored 81.3 nDCG@5 on ViDoRe v1 vs 67.0 for the best OCR+captioning pipeline (Unstructured + captioning + BGE-M3) ([ViDoRe v2 post](https://huggingface.co/blog/manu/vidore-v2)). ViDoRe V3 (Jan 2026, 26k pages, 3,099 queries, 6 languages) is the current benchmark; current ColQwen3-family models reach ~60–62 nDCG@10 on V3 (Tomoro colqwen3-embed-8b 61.6; OpenSearch Ops-Colqwen3-4B ~60.2 at 128-d), and NVIDIA's Nemotron ColEmbed V2 reported top results as of Feb 2026 ([Qdrant course page](https://qdrant.tech/course/multi-vector-search/module-2/colpali-family/), [Nemotron ColEmbed V2](https://arxiv.org/pdf/2602.03992)). Rankings move monthly; most scores are self-reported. fastembed ships `Qdrant/colpali-v1.3-fp16` and (v0.8.0) ColModernVBERT.

**Qdrant support.** Multivectors since 1.10: a point stores a matrix of same-size vectors, comparator `max_sim`; hard limit `num_sub_vectors × dim < 1,048,576` ([vectors doc source](https://github.com/qdrant/landing_page/blob/master/qdrant-landing/content/documentation/manage-data/vectors.md)). Recommended pattern (Qdrant blog + tutorial): mean-pool the 32×32 patch grid by rows (1,030 → ~32–38 vectors) and index *that* with HNSW for stage 1, keep the full multivector with `hnsw_config.m = 0` (no graph) and rescore the top-N candidates with it in a prefetch → multivector query; 13× faster with near-identical quality on Qdrant's dataset ([blog](https://qdrant.tech/blog/colpali-qdrant-optimization/), [tutorial](https://qdrant.tech/documentation/tutorials-search-engineering/pdf-retrieval-at-scale/)). Binary quantization applies to multivectors too.

**Cost.** Storage 50–100× a single dense vector per page/chunk; GPU needed for ColPali-family encoders; query-time MaxSim over candidates is cheap once prefetch narrows them. Worth it for scanned/visual corpora (slides, forms, charts) and as a *reranking* stage over text chunks; not as the primary index for large text corpora.

### B3. Chunking and context enrichment

- **Structure-aware / Docling HybridChunker**: `HierarchicalChunker` emits one chunk per document element (merging list items), attaches headings + captions; `HybridChunker` then splits only chunks that exceed the embedding model's tokenizer limit and merges undersized siblings sharing the same headings (`merge_peers`), with `repeat_table_header` for tables spanning chunks; `chunk.meta` carries provenance (doc items → page numbers/bboxes) and `contextualize(chunk)` returns the heading-enriched text to embed ([docling chunking doc source](https://github.com/docling-project/docling/blob/main/docs/concepts/chunking.md)). This is the right default.
- **Contextual retrieval / contextual chunk headers** (Anthropic, Sept 2024): prepend a 50–100-token LLM-written "where does this chunk sit in the document" blurb before embedding and BM25-indexing; numbers above; one-time cost ≈ $1.02 per million document tokens with prompt caching ([Anthropic](https://www.anthropic.com/news/contextual-retrieval)). Cheaper deterministic variant: prepend `title > H1 > H2` breadcrumbs (what Docling `contextualize()` already does) and only pay for LLM context on documents where heading structure is poor.
- **Late chunking** (Jina/Weaviate, arXiv 2409.04701): embed the whole long document through a long-context encoder, then mean-pool token embeddings per chunk span; +2.7–3.6% nDCG@10 on BEIR subsets, no training, needs an 8k+ context embedding model and the full token-level outputs — not possible through a NIM embeddings API that returns pooled vectors only. Skip unless we self-host the encoder ([paper](https://arxiv.org/html/2409.04701v3)).
- **Propositions** (Dense X Retrieval, EMNLP 2024): LLM-decompose text into atomic self-contained facts; +12.0 Recall@5 avg over passages with unsupervised SimCSE (secondary summary); LLM cost scales with corpus size and answers lose context — best used for FAQ-style corpora, not as the default unit ([paper](https://arxiv.org/pdf/2312.06648)).
- **Parent–child / small-to-big**: index small children (≈128–256 tokens) for precision, return the parent (≈1–2k tokens or the section) to the LLM. Dify, LlamaIndex (`HierarchicalNodeParser` + `AutoMergingRetriever`), LangChain `ParentDocumentRetriever` and RAGFlow all ship it; no single canonical paper, but it is the standard mitigation for the chunk-size precision/context trade-off. On Qdrant: store `parent_id`, `section_path`, `page` in payload; dedupe by parent with `query_points_groups(group_by="parent_id")` (1.11+) or in app code.
- **RAPTOR** (ICLR 2024): recursively cluster + summarise chunks into a tree; retrieve across levels; +20 points absolute on QuALITY with GPT-4 ([paper](https://proceedings.iclr.cc/paper_files/paper/2024/hash/8a2acd174940dbca361a6398a4f9df91-Abstract-Conference.html)). Costs an LLM pass over the entire corpus at every level; helps "summarise/compare across the document" questions. v2 candidate; a cheaper proxy is to index per-document and per-section LLM summaries as extra points with `level` in payload.
- **Semantic chunking**: embedding-similarity breakpoints. The NAACL Findings 2025 study concludes the extra compute is "not justified by consistent performance gains"; fixed-size often wins on realistic documents ([Qu et al.](https://arxiv.org/html/2410.13070v1), [Vectara summary](https://vectara.com/blog/is-semantic-chunking-worth-the-computational-cost)). Skip.

### B4. Query transformation, routing, corrective and agentic loops

- **HyDE** (arXiv 2212.10496): LLM writes a hypothetical answer; embed that. Beats unsupervised Contriever, roughly matches fine-tuned retrievers in the paper; an Elastic case study found +50% precision/recall on 2 of 3 hand-picked short queries ([Elastic](https://www.elastic.co/search-labs/blog/hyde-semantic-search-elasticsearch)). Adds one LLM call (~0.5–2 s). Useful for short/underspecified queries against formal text; hurts when the LLM hallucinates specifics. Use behind a router, not always-on.
- **Multi-query / RAG-Fusion**: generate N paraphrases, retrieve each, RRF. Increases recall, but a 2026 study shows Hit@10 can even drop (0.51 → 0.48) after rerank+truncate, with added latency ([arXiv 2603.02153](https://arxiv.org/abs/2603.02153v1)); an earlier RAGElo study found better completeness but worse precision. Use only for decomposition of genuinely multi-part questions.
- **Step-back prompting** (ICLR 2024): ask an abstract "principle" question first; +7 (MMLU Physics), +11 (Chemistry), +27 (TimeQA), +7 (MuSiQue) points with PaLM-2L ([paper](https://arxiv.org/abs/2310.06117v1)). Cheap; good for "why/how" questions over technical docs.
- **Query decomposition**: split multi-hop questions into sub-queries, retrieve per sub-query, synthesise. The NVIDIA blueprint ships this plus LLM-generated metadata filter expressions; FRAMES shows the headroom: Gemini-1.5-Pro naive 40.8% → BM25 single-step 47.4% → multi-step retrieval 66% → oracle docs 72.9% ([FRAMES](https://alphaxiv.org/overview/2409.12941v3)).
- **Routing / Adaptive-RAG** (NAACL 2024): a small classifier (T5-large in the paper) routes to no-retrieval / single-step / multi-step; improves accuracy–latency trade-off across open-domain QA ([paper](https://aclanthology.org/2024.naacl-long.389)). Practical version: LLM-judged intent (chit-chat / lookup / multi-hop / summarise) → pipeline choice.
- **Self-RAG** (ICLR 2024): fine-tuned 7B/13B generator emits reflection tokens (Retrieve, IsRel, IsSup, IsUse); beats ChatGPT and retrieval-augmented Llama2-chat on PopQA/PubHealth/long-form citation accuracy ([paper](https://arxiv.org/abs/2310.11511v1)). Requires training; the *idea* (grade relevance, grade support) is usually implemented as prompts.
- **CRAG** (arXiv 2401.15884): lightweight retrieval evaluator → Correct / Incorrect / Ambiguous → refine (decompose-recompose) or fall back to web search; +7.0 PopQA, +14.9 Biography FactScore, +36.6 PubHealth over RAG on a Self-RAG-7B base (smaller gains on plain Llama2-7B) ([paper](https://arxiv.org/html/2401.15884v3)). The LangGraph "CRAG" pattern is the easiest production approximation: grade top-k, re-query if too few are relevant.
- **Agentic / deep-research loops** (survey arXiv 2501.09136 v4, Apr 2026): plan → retrieve → reflect → retrieve again, with tool use; RAGFlow's "thinking modes", R2R Deep Research, NVIDIA plan-and-execute, Open WebUI `ENABLE_KB_EXEC`, LightRAG mix mode all implement variants. Cost: 3–10× the LLM calls of single-shot RAG; reserve for explicit "deep" mode.

### B5. Reranking

| Model | Type | License | Notes |
|---|---|---|---|
| `nvidia/llama-nemotron-rerank-1b-v2` (NIM) | cross-encoder, Llama-3.2-1B | NVIDIA Open Model + Llama 3.2 Community | 8192 tokens, 26 languages, FP16 needs ~7.3 GB GPU; released on build.nvidia.com 2026-02-27; the blueprint default ([NIM card](https://docs.api.nvidia.com/nim/reference/nvidia-llama-nemotron-rerank-1b-v2)) |
| `BAAI/bge-reranker-v2-m3` | cross-encoder, 568M | Apache-2.0 | BEIR 67.64 nDCG@10 ([Querit](https://arxiv.org/pdf/2606.19037)); ~80–150 ms / 20 docs on a T4 (secondary, [ianas](https://ianas.fr/en/blog/2026/06/07/reranker-comparatif-cohere-bge-jina-voyage/)); in fastembed 0.9.0 incl. int8 |
| `Qwen/Qwen3-Reranker-0.6B/4B/8B` | LLM-based pointwise | Apache-2.0 | 8B: 68.97 BEIR (best open); 0.6B: 59.59 ([Querit](https://arxiv.org/pdf/2606.19037)) |
| `mixedbread-ai/mxbai-rerank-v2` (0.5B/1.5B) | cross-encoder | Apache-2.0 | vendor-reported strong BEIR; fast 1.5B |
| `jinaai/jina-reranker-v3` | listwise-ish | CC-BY-NC-4.0 | 66.83 BEIR; non-commercial |
| Contextual AI rerank v2 | open weights | — | claims parity with Qwen3-8B at lower latency (vendor) ([blog](https://contextual.ai/blog/rerank-v2)) |
| Cohere Rerank 4 (Fast/Pro) | API | commercial | Dec 2025; 32k context, 100+ languages; ~$0.0025/search (OpenRouter) ([OCI notes](https://docs.oracle.com/en-us/iaas/releasenotes/generative-ai/cohere-rerank-4.htm)) |
| RankGPT / RankZephyr / RankVicuna | listwise LLM | — | RankGPT-GPT-4 avg nDCG@10 53.68 across TREC+BEIR, beats monoT5-3B (secondary); RankZephyr-7B matches/exceeds GPT-4 on TREC DL ([RankZephyr](https://arxiv.org/abs/2312.02724v1)) |

Latency vs quality: cross-encoders on ~50–100 candidates cost 50–300 ms on a GPU and dominate quality gains (Anthropic: −49% → −67% failure). LLM listwise rerankers add seconds and are best reserved for a final top-20 → top-5 pass in "deep" mode. Rerank *after* fusion, before parent expansion, and rerank on the child text + heading context.

### B6. Embedding models (open, Oct 2026)

| Model | Dim (MRL) | Context | License | Notes |
|---|---|---|---|---|
| `nvidia/llama-nemotron-embed-1b-v2` (NIM) | 2048 (384/512/768/1024/2048) | 8192 | NVIDIA Open Model + Llama 3.2 | 26 languages; the blueprint default ([NIM card](https://docs.api.nvidia.com/nim/reference/nvidia-llama-nemotron-embed-1b-v2)) |
| `Qwen/Qwen3-Embedding-0.6B/4B/8B` | 1024/2560/4096 (32→max) | 32k | Apache-2.0 | 8B was #1 MTEB-multilingual (70.58) at release (Jun 2025); still top-5 in Sept 2026 ([card via search](https://huggingface.co/Qwen/Qwen3-Embedding-4B)); 0.6B in fastembed 0.8.1 |
| `BAAI/bge-m3` | 1024 | 8192 | MIT | dense + sparse + ColBERT in one pass; multilingual workhorse |
| `nvidia/NV-Embed-v2` | 4096 | 32k | NVIDIA non-commercial/research (secondary) | strong but license-restricted |
| `jinaai/jina-embeddings-v4` | 2048 (→128) | 32k | Qwen Research License (non-commercial) | multimodal, late-interaction mode |
| `jinaai/jina-embeddings-v5-text-small` | 1024 (→32) | 32k | CC-BY-NC-4.0 | non-commercial |
| `google/embeddinggemma-300m` | 768 (512/256/128) | 2k | Gemma terms | mid-table on MTEB; tiny; in fastembed 0.8.1 |
| `Snowflake/snowflake-arctic-embed-l-v2.0` | 1024 (→256) | 8192 | Apache-2.0 | good multilingual/latency |
| `nomic-ai/nomic-embed-text-v2-moe` | 768 (→256) | 512–8192 (sources conflict) | Apache-2.0 | MoE |
| `microsoft/harrier-oss-v1-27b` | — | — | MIT | reported #1 MTEB multilingual v2 (Sept 2026, secondary) — too large for us |

Sources: [premai 2026 ranking](https://www.premai.io/blog/best-embedding-models-for-rag-2026-ranked-by-mteb-score-cost-and-self-hosting/), [bentoml guide](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models), [jina v4](https://jina.ai/models/jina-embeddings-v4/). The live MTEB board changes monthly; verify before locking a choice.

Quantization in Qdrant: scalar int8 (≈4× smaller, negligible loss), binary (≈32×, 40× faster; needs `rescore: true` + `oversampling` ≥2; 0.98 recall@100 at 4× oversampling for 1536-d OpenAI vectors; low-dim vectors suffer without rescoring), 4-bit TurboQuant storage datatype since 1.19 (vectors stored only as 4-bit, ~1/8 of fp32), float16 datatype, "inline storage" (1.16) putting quantized vectors inside HNSW nodes (20 → 211 QPS at low RAM in Qdrant's benchmark). Matryoshka: store the full vector, run stage-1 on a truncated named vector (e.g. 512-d, binary) and rescore with the full one via prefetch (Qdrant's documented MRL pattern; set `m=0` on the rescoring-only vector). ([quantization docs](https://qdrant.tech/documentation/manage-data/quantization/), [BQ article](https://qdrant.tech/articles/binary-quantization/), [1.16 blog source](https://github.com/qdrant/landing_page/blob/master/qdrant-landing/content/blog/qdrant-1.16.x.md), [1.19.0 notes](https://github.com/qdrant/qdrant/releases/tag/v1.19.0))

### B7. Document parsing

| Tool | Version / status | License | Formats | Strengths / weaknesses |
|---|---|---|---|---|
| **Docling** (IBM) | v2.140.0 (2026-10-16), 69k stars | MIT | PDF, DOCX, PPTX, XLSX, HTML, images, Markdown, AsciiDoc, LaTeX, CSV, ODF, iWork, audio (ASR), + external VLMs (MinerU, Chandra, dots) | Layout model + TableFormer → typed `DoclingDocument`; optional OCR (RapidOCR/PP-OCRv6, Tesseract, EasyOCR, KServe remote); VLM pipeline with granite-docling-258M / granite-vision-4.1-4b producing the same document model; HybridChunker; exports JSONL ready for Qdrant. Weaker on heavy-OCR benchmarks (olmOCR-bench ~50 overall, 64 on born-digital vs ~83 for Marker/MinerU, secondary) ([releases](https://github.com/docling-project/docling/releases), [docling.org](https://docling.org/)) |
| **MinerU** (OpenDataLab) | 4.0 line, 82k stars | "MinerU Open Source License" (Apache-2.0 + conditions) | PDF, images, DOC(X), PPT(X), XLS(X), RTF, ODF, EPUB, OFD, HTML, CSV (native via DocVortex) | Four tiers (flash/basic/standard/advanced); MinerU2.5 decoupled VLM; tops OmniDocBench (self-reported); best for scanned/CJK/formula/table-heavy PDFs; needs GPU (≥8 GB VRAM) for the good tiers ([README](https://github.com/opendatalab/MinerU)) |
| **Marker** (Datalab) | 2.x, 40.5k stars | Apache-2.0 code; **weights under modified OpenRAIL-M: free only <$5M revenue/funding** | PDF, images, PPTX, DOCX, XLSX, HTML, EPUB | Surya VLM; balanced mode 76.0 overall / 83.5 born-digital on olmOCR-bench (self-reported), 2.9 pages/s on B200; `--use_llm` for tables across pages ([README](https://github.com/datalab-to/marker)) |
| **unstructured** | active, 15.6k stars | Apache-2.0 | many | Partitioning + chunking library; quality behind the VLM/layout parsers on 2026 benchmarks; hosted platform is the focus ([repo](https://github.com/Unstructured-IO/unstructured)) |
| **PyMuPDF4LLM** | now inside `pymupdf-2.x`; old repo is a placeholder | AGPL-3.0 (commercial license available) | PDF (+Office via conversion) | Fastest text-layer → Markdown with headers/tables/page chunks; reading order breaks at figures; AGPL is a problem for a product ([repo](https://github.com/pymupdf/RAG)) |
| **LlamaParse** | API (v2, Jan 2026) | commercial | 50+ | Agentic modes; credit pricing |
| **Reducto** | API; r-1 model (Sept 2026) at 1¢/page | commercial | — | Strong tables (RD-TableBench is its own benchmark) |
| **NVIDIA nv-ingest / NeMo Retriever Extraction** | 26.8.1 GA, 26.3 LTS | Apache-2.0 (code); NIM model licenses | PDF, HTML, images, TXT (+ audio) | Page-element, table-structure, graphic-element and `nemotron-ocr-v1` NIMs; library mode (<100 PDFs) or Kubernetes service; GPU required ([README](https://github.com/NVIDIA/nv-ingest)) |

Benchmarks are inconsistent across harnesses (OmniDocBench v1.5 vs v1.6, olmOCR-bench, small custom sets); the only safe statement is: MinerU ≥ Marker > Docling > PyMuPDF4LLM on OCR-heavy PDFs, and all are close on born-digital text ([dev.to comparison](https://dev.to/moksh/pdf-parsers-for-rag-in-2026-when-open-weights-beat-the-frontier-models-4o9n), [9-tool benchmark](https://github.com/pdfmarkdownapp/pdf-to-markdown-benchmark)).

**Best default for self-hosted PDF/DOCX/PPTX/XLSX: Docling.** Reasons: MIT with no revenue clauses; the only one with native, maintained parsers for all four Office formats plus a structured document model that survives into chunking (headings, captions, table cells, page provenance for citations); CPU-capable; same output whether you later switch its PDF backend to the VLM pipeline or route hard scans to MinerU/nv-ingest. Add MinerU (GPU) or nv-ingest as a configurable backend for scanned/visual-heavy PDFs.

### B8. GraphRAG family — when it helps, what it costs

Evidence:
- GraphRAG-Bench ([arXiv 2506.05690](https://www.alphaxiv.org/abs/2506.05690)): on complex reasoning HippoRAG 2 reached 53.38% vs 42.93% for reranked basic RAG; on fact retrieval reranked RAG beat GraphRAG-local 60.92 vs 49.29; on medical summarisation reranked RAG 65.75 vs HippoRAG 2 63.08. Index build ranged from ≈9.2M tokens (HippoRAG 2) to ≈115.5M tokens (Microsoft GraphRAG) on the same corpus.
- "RAG vs GraphRAG: a systematic evaluation" ([arXiv 2502.11371](https://arxiv.org/pdf/2502.11371)): RAG wins single-hop (NQ); GraphRAG methods (HippoRAG 2, community-GraphRAG local) win multi-hop.
- RAGU ([arXiv 2607.11683](https://arxiv.org/pdf/2607.11683)): LightRAG weakest at every level on GraphRAG-Bench (attributed to single-pass free-form extraction); HippoRAG 2 led factoid retrieval.
- HippoRAG 2 paper: +7% on associativity tasks vs NV-Embed-v2, +9.5 F1 on 2Wiki, no regression on NQ; indexing far cheaper than GraphRAG/RAPTOR/LightRAG ([paper](https://arxiv.org/pdf/2502.14802)).
- Microsoft's own docs: graph extraction ≈ 75% of indexing cost; FastGraphRAG (NLP extraction) cuts it but yields a noisier graph; Global search is "resource-intensive"; DRIFT is the better local mode ([index methods](https://github.com/microsoft/graphrag/blob/main/docs/index/methods.md), [query overview](https://github.com/microsoft/graphrag/blob/main/docs/query/overview.md)); LazyGraphRAG not yet released in OSS.

Takeaway: graphs pay off for (a) multi-hop/relational questions across documents and (b) "what are the main themes" global questions; they lose to hybrid+rerank on lookup, and indexing costs 10–100× an embedding pass plus an LLM call per chunk. Put it behind the query router in v2, implement as HippoRAG-style (entities + facts + passage nodes, PPR) or LightRAG (which already runs on Qdrant for vectors), and store the graph in Postgres/Neo4j/Memgraph.

### B9. Evaluation

Tools:
- **RAGAS** (vibrantlabsai/ragas, 16.0k stars, Apache-2.0; note the org moved from `explodinggradients`; last push Feb 2026). Current RAG metric names: Context Precision, Context Recall, Context Entities Recall, Noise Sensitivity, Response Relevancy, Faithfulness, Multimodal Faithfulness, Multimodal Relevance; agent metrics: Topic Adherence, Tool Call Accuracy, Tool Call F1, Agent Goal Accuracy ([metrics doc source](https://github.com/vibrantlabsai/ragas/blob/main/docs/concepts/metrics/available_metrics/index.md)). Also a test-set generator (knowledge-graph-based synthetic questions).
- **DeepEval** (18.9k, Apache-2.0): pytest-style `assert_test` / `deepeval test run`; RAG metrics Answer Relevancy, Faithfulness, Contextual Precision/Recall/Relevancy; G-Eval and DAG custom judges; agentic metrics (Task Completion, Tool Correctness …); synthetic data generation ([README](https://github.com/confident-ai/deepeval)).
- **Arize Phoenix** (11.9k; Elastic License 2.0): OpenTelemetry/OpenInference tracing + evals; good for inspecting retrieved chunks per trace.
- **Langfuse** (35.9k; MIT core, some `ee/`): self-hosted tracing, prompt management, datasets, LLM-as-judge evals; acquired by ClickHouse (secondary).
- **TruLens** (3.6k, MIT): "RAG triad" (context relevance, groundedness, answer relevance); slower roadmap.
- **ARES** (0.7k, Apache-2.0): fine-tuned judge classifiers + prediction-powered inference; last push Mar 2025 — academic.

Benchmarks: BEIR (zero-shot retrieval, nDCG@10), MTEB (embeddings; English v2 / Multilingual v2 boards), BRIGHT (reasoning-intensive retrieval; best models <30 nDCG@10, BM25 ~8.5 on MM-BRIGHT text ([paper](https://arxiv.org/abs/2407.12883))), FRAMES (824 multi-hop Wikipedia questions; multi-step 66% vs oracle 72.9%), RAGBench (100k examples, 5 domains, TRACe = Relevance / Utilization / Adherence / Completeness; a fine-tuned DeBERTa-large beats few-shot LLM judges ([paper](https://arxiv.org/pdf/2407.11005))), LongBench (long-context QA), ViDoRe V3 (visual docs), GraphRAG-Bench.

**Minimum sensible harness for our engine (v1):**
1. A versioned, domain-specific gold set: 150–300 questions over the real corpus with (question, expected answer, gold chunk/page ids, question type ∈ {lookup, multi-hop, summarise, table, no-answer}). Seed with RAGAS/DeepEval synthetic generation, then human-edit; keep 20% held out for fusion-weight/rerank tuning.
2. Retrieval metrics computed offline, no LLM judge: Recall@k and MRR / nDCG@10 against gold chunk ids at k = 5/20/50, per question type and per pipeline stage (dense only, sparse only, fused, reranked). This is what catches regressions.
3. Generation metrics with an LLM judge: RAGAS Faithfulness + Response Relevancy + Context Precision/Recall (or the DeepEval equivalents), plus a citation-correctness check (does each cited chunk support the sentence).
4. Latency/cost per stage (p50/p95) logged with traces (Langfuse self-hosted or Phoenix).
5. Run as a CI job (DeepEval's pytest runner is the simplest) with thresholds; store runs so pipeline A/B comparisons are a diff.

### B10. Qdrant specifics (1.19.x, Aug–Oct 2026)

Release line: 1.16.0 (2025-11-19), 1.17.0 (2026-02-20), 1.18.0 (2026-05-11), 1.19.0 (2026-08-05), 1.19.2 (2026-10-05) ([releases](https://github.com/qdrant/qdrant/releases)). 35.1k stars, Apache-2.0. Python client `qdrant-client` tracks server minors; fastembed 0.9.0 (2026-10-07).

- **Query API** (`/points/query`, 1.10+): one endpoint for dense, sparse, multivector, recommend/discover, `prefetch` sub-requests (nestable), fusion, formula scoring, grouping. Old `search` endpoints removed from OpenAPI in 1.19.
- **Fusion**: `rrf` (k configurable 1.16, weights 1.17), `dbsf` (1.11). Prefetch `limit` must be ≥ `limit + offset`. Fusion in prefetch is per-shard.
- **Score boosting / formula queries** (1.14+): combine `$score` with payload fields and decay functions (e.g., recency boost, source-type weight) on top of a fused prefetch. A main query can't be both fusion and formula; nest fusion in a prefetch.
- **Relevance feedback** (1.17): rescoring by positive/negative example points.
- **Multivectors**: `max_sim` comparator; `num_vectors × dim < 1,048,576` per point.
- **Sparse vectors**: exact inverted index, dot product only, `modifier: idf`; per-query `idf` corpus scoping (1.19) for multitenancy; `enable_hnsw: false` on payload indexes used only with sparse search (1.17).
- **Named vectors**: multiple spaces per point; add/delete named vectors on an existing collection since 1.18 (existing points need re-upsert to fill them).
- **Datatypes**: float32 (default), float16, uint8, Turbo4 (1.19, 4-bit storage). **Quantization**: scalar int8, binary (1-bit; also 1.5-/2-bit variants in the course material), product; `always_ram`, `rescore`, `oversampling` per query; inline storage in HNSW nodes (1.16).
- **Payload indexes**: keyword (prefix matching 1.19), integer (lookup/range flags), float, bool, geo, datetime, uuid, text. **Full-text** index: tokenizers word/whitespace/prefix/multilingual (charabia; vaporetto for Japanese), lowercase, ASCII folding (1.16), Snowball stemming per language, stopword lists, phrase matching (must be enabled at index creation), `text_any` condition (1.16). Full-text index is for *filtering*; ranking by lexical relevance is done with BM25 sparse vectors. Memory tiers per index: pinned / cached / cold (1.19).
- **Filterable HNSW + ACORN** (1.16): extra graph edges from indexed payload values; `acorn` per-query option for combined low-selectivity filters (53% → 97% accuracy at 10× latency in Qdrant's benchmark).
- **Multitenancy**: (1) payload partitioning with a keyword/uuid index marked `is_tenant: true` (1.11; co-locates tenant data; set `m=0`, `payload_m=16` for per-tenant graphs); (2) custom shard keys (1.7) for large tenants; (3) tiered multitenancy (1.16): small tenants in a shared fallback shard, promoted to dedicated shards via `replicate_points` with no downtime (`shard_number: 1` required; suggested promotion threshold ≈20k points; ≤~1000 dedicated shards). ([multitenancy source](https://github.com/qdrant/landing_page/blob/master/qdrant-landing/content/documentation/manage-data/multitenancy.md))
- **Strict mode** (1.13+): per-collection `strict_mode_config` — reject filtering on unindexed fields (`unindexed_filtering_retrieve: false`), caps on query limit, timeout, read/write rate limits per replica, payload size, max payload-index count (1.16), batch size (1.17 preview), memory-pressure rejection (1.18; `max_resident_memory_percent` deprecated in 1.19 for the global quota API). Enabled by default on Qdrant Cloud; enabling without specifying limits does nothing ([admin doc](https://qdrant.tech/documentation/ops-configuration/administration/)).
- **Conditional updates** (1.16): upsert only if a payload condition holds (e.g., `embedding_version == N`) — handy for model migrations. **`update_mode`** on upserts (1.17).
- **fastembed**: ONNX-runtime embeddings (dense, sparse BM25/SPLADE/miniCOIL, ColBERT/ColPali/LateOn, cross-encoder rerankers incl. bge-reranker-v2-m3, image/CLIP, Model2Vec); the client can embed inline (`client.add`/`query` with `fastembed` models) or you call it explicitly; GPU via `fastembed-gpu`. For our stack: use fastembed for BM25 sparse + optional local reranker fallback; use NIM for dense embeddings and the primary reranker.
- **Operations**: upgrade one minor at a time; strict mode + payload indexes created *before* ingestion (filterable HNSW edges are built at index time); snapshots; `replicate_points`; global quota API (1.19); routing tokens for read affinity (1.19).

---

## Part C — Recommended reference architecture

Design goal: a modular, measurable engine whose v1 is "hybrid + structure-aware chunks + rerank + citations + evals", with clean seams for the v2 tiers (visual late-interaction, graph, agentic).

### C.1 Ingestion pipeline (order matters)

1. **Intake & normalisation** — FastAPI upload / connector → object store (S3-compatible) → Postgres `documents` row (tenant, source, ACL, checksum, version). Dedupe by checksum. Rationale: Qdrant is not the system of record; every framework that scales (NVIDIA, Onyx, RAGFlow) keeps a relational catalogue beside the vector DB.
2. **Parse → `DoclingDocument`** — Docling default pipeline (layout + TableFormer, OCR auto-on for image-only pages, RapidOCR engine). Config flag to route PDFs with low text-layer coverage or heavy figures to MinerU (GPU) or nv-ingest. Persist the JSON document (page map, bboxes) for citation rendering and re-chunking without re-parsing.
3. **Chunk** — Docling `HybridChunker` with the tokenizer of the embedding model (nemotron-embed: 8192 max; target child chunk ≈ 256–400 tokens, max 512) and `merge_peers=True`, `repeat_table_header=True`. Build **parent** units = section (heading-bounded, capped ≈1.5–2k tokens) and keep `parent_id`, `section_path`, `page_start/end`, `bbox`, `element_type` (text/table/list/caption) in payload. Rationale: structure-aware beats semantic chunking on evidence; parent/child fixes the precision-vs-context trade-off.
4. **Contextualise** — text to embed = `contextualize(chunk)` (doc title + heading breadcrumb + chunk). Optional LLM "contextual retrieval" blurb (50–100 tokens, NIM LLM, cached) only for documents whose heading structure is weak (heuristic: <2 heading levels or >40% chunks with no heading). Rationale: 35–49% fewer retrieval failures for ≈$1 per million tokens one-time; make it a per-collection switch.
5. **Embed** — dense via NIM `llama-nemotron-embed-1b-v2` (2048-d, or 1024-d MRL if storage matters; `input_type=passage`), batched async with retries; sparse BM25 via fastembed `Qdrant/bm25` (stemmer + stopwords per language) computed on the same contextualised text. Rationale: one dense + one lexical signal is the evidence-backed minimum; both multilingual-capable.
6. **Upsert to Qdrant** — one collection per environment, tenants by payload (`tenant_id` keyword index with `is_tenant=true`); named vectors `dense` (int8 scalar quantization, `always_ram=true`, originals on disk) and sparse `bm25` (IDF modifier); payload indexes created before ingest: `tenant_id`, `doc_id`, `parent_id`, `source_type`, `created_at` (datetime), `section_path` (keyword), `page`, and a `text` full-text index (multilingual tokenizer, stemming) for filter-style "must contain" queries. Strict mode on (`unindexed_filtering_retrieve=false`, sane `max_query_limit`). Use conditional updates keyed on `embedding_version` for re-embedding migrations.
7. **Optional enrichment (v2)** — per-document and per-section LLM summaries indexed as extra points with `level ∈ {doc, section, chunk}` (cheap RAPTOR-lite for "summarise/compare" questions); ColPali/ColQwen page embeddings in a separate `pages` collection (mean-pooled rows as HNSW vector + full multivector with `m=0`); HippoRAG/LightRAG-style entity/fact extraction into Postgres/graph store.
8. **Index QA** — on each ingest run compute chunk stats (tokens, empty/dup chunks, OCR confidence) and run a smoke retrieval over the doc's own synthetic questions.

### C.2 Query pipeline

1. **Pre-processing** — tenant/ACL filter construction (always a Qdrant `must` filter on `tenant_id` + ACL fields; never post-filter), language detection, conversation-aware query condensation for follow-ups (one small NIM LLM call, skipped on first turn).
2. **Router (lightweight)** — rule + LLM classifier → `lookup` (default), `multi_hop`, `summarise`, `table/numeric`, `chit_chat/no_retrieval`. v1 implements only `lookup` and `no_retrieval`; others fall through to lookup but are logged for the eval set.
3. **Retrieval (Qdrant Query API, one round-trip)** — `prefetch`: dense top-100 (NIM query embedding, `input_type=query`) + BM25 top-100, both with the same filter; `query = rrf` (weights tuned on the held-out split; start 1.0/1.0); `limit=50`; optional formula rescoring prefetch for recency/source boosts. Optional HyDE / step-back rewrite only when the router says `multi_hop` or the query is <5 tokens.
4. **Rerank** — NIM `llama-nemotron-rerank-1b-v2` over the 50 fused children (query + contextualised child text); keep top-8–12; fastembed `bge-reranker-v2-m3` as a local fallback. Drop candidates below a score threshold learned from the eval set (this is the cheap CRAG-style "is anything relevant?" gate that enables honest "not found" answers).
5. **Context assembly** — expand survivors to parents, dedupe by `parent_id`, order by document then page, cap at a token budget (≈6–8k tokens), attach stable citation ids `[doc:page:chunk]`, render tables as Markdown from Docling cells.
6. **Generate** — NIM LLM (blueprint default `nemotron-3-super-120b-a12b`, or a smaller Nemotron for latency) with a grounded-answer prompt requiring inline citations and an explicit "insufficient evidence" path; stream tokens. Post-check: every citation id must exist in the context (hard filter) and, in v2, an LLM "is each cited sentence supported" judge sampled at 10% for monitoring.
7. **Multi-hop / deep mode (v2)** — LangGraph (or a plain async state machine) loop: decompose → retrieve per sub-question (same stage 3–4) → grade coverage → iterate ≤3 → synthesise; graph retrieval (HippoRAG/LightRAG mix) added as a parallel retriever behind the router for `multi_hop`; ColPali page retrieval for `table/figure` questions on visual corpora.
8. **Telemetry** — every stage logged with ids and timings (OpenTelemetry → Langfuse/Phoenix), including the full candidate lists so eval replays are possible.

### C.3 What is worth it at v1 vs later

| Technique | v1 | Later | Reason |
|---|---|---|---|
| Docling parse + HybridChunker + parent/child | yes | | Evidence-backed, cheap, MIT |
| Heading-breadcrumb contextualisation | yes | | free |
| LLM contextual-retrieval blurbs | per-collection switch | | one-time cost, big recall gain on poorly structured docs |
| Hybrid dense + BM25 with RRF (Qdrant native) | yes | | +latency ~1 ms, large recall gain |
| Cross-encoder rerank (NIM) + relevance threshold | yes | | largest single quality lever |
| Citations with page/bbox provenance | yes | | user trust; Docling gives it for free |
| Eval harness (gold set, Recall@k, RAGAS/DeepEval, CI) | yes | | nothing else can be tuned without it |
| Multitenancy via payload + strict mode + int8 quantization | yes | | operational hygiene |
| Query condensation for chat follow-ups | yes | | otherwise follow-up questions fail |
| Router + HyDE/step-back for hard queries | minimal | full | only helps a subset; needs eval to prove |
| Weighted RRF / formula boosts | | yes | needs the eval split first |
| Multi-hop decomposition loop (CRAG-style) | | yes | 3–10× LLM cost; only for `multi_hop` |
| RAPTOR-lite summaries | | yes | summarise/compare questions |
| GraphRAG tier (HippoRAG 2 / LightRAG) | | yes, behind router | wins only on relational multi-hop; indexing cost |
| ColPali/ColQwen page retrieval | | yes, for visual corpora | GPU encoder, 50–100× storage |
| Binary quantization / Turbo4 | | when >10M vectors | int8 is enough at v1 |
| DSPy optimisation of prompts | | yes | once eval set exists |
| Late chunking, propositions, semantic chunking | no | maybe never | weak or negative evidence for our setting |

### C.4 Default models (self-hosted / NIM)
- Dense embeddings: `nvidia/llama-nemotron-embed-1b-v2` (2048-d, 8192 ctx, MRL). Alternative if NIM unavailable: `Qwen/Qwen3-Embedding-0.6B` (1024-d, Apache-2.0) or `BAAI/bge-m3` (also yields sparse).
- Lexical: fastembed `Qdrant/bm25` (stemmer+stopwords); evaluate `Qdrant/minicoil-v1` for English-only corpora.
- Reranker: `nvidia/llama-nemotron-rerank-1b-v2` (NIM); fallback `BAAI/bge-reranker-v2-m3` (fastembed, Apache-2.0); `Qwen3-Reranker-4B/8B` if a GPU is spare and quality trumps latency.
- LLM: `nvidia/nemotron-3-super-120b-a12b` for answers; a smaller Nemotron/Llama NIM for routing, condensation and contextual blurbs.
- Parser: Docling (default) → MinerU/nv-ingest for scans.
- Visual (v2): `nemotron-colembed` or ColQwen3-family via fastembed/colpali-engine.
- Eval: DeepEval (CI) + RAGAS metrics; Langfuse for traces.

### C.5 Risks and open questions
- NIM model licenses (Llama 3.2 Community + NVIDIA Open Model) are commercial-OK but not OSI; keep an Apache-2.0 fallback path (Qwen3-Embedding + bge-reranker) wired and tested.
- Qdrant moves fast (three minors in 2026); pin server and client minors together and test `prefetch`/fusion behaviour on upgrade.
- Marker and Morphik are not usable as commercial defaults due to weight/BSL licenses; Dify and Open WebUI carry branding/multi-tenant clauses — none of these should be embedded.
- The multi-query/RAG-fusion literature is mixed in 2026; do not add fusion stages without an eval delta.
- Most parser benchmark numbers are self-reported; run our own 20-document parse bake-off (Docling vs MinerU vs nv-ingest) on the real corpus before freezing the default.

---

## Key sources (deduplicated)

- Qdrant: [releases](https://github.com/qdrant/qdrant/releases) · [1.19.0 notes](https://github.com/qdrant/qdrant/releases/tag/v1.19.0) · [1.16 blog (source)](https://github.com/qdrant/landing_page/blob/master/qdrant-landing/content/blog/qdrant-1.16.x.md) · [1.17 blog](https://qdrant.tech/blog/qdrant-1.17.x/) · [hybrid queries (source)](https://github.com/qdrant/landing_page/blob/master/qdrant-landing/content/documentation/search/hybrid-queries.md) · [indexing (source)](https://github.com/qdrant/landing_page/blob/master/qdrant-landing/content/documentation/manage-data/indexing.md) · [vectors (source)](https://github.com/qdrant/landing_page/blob/master/qdrant-landing/content/documentation/manage-data/vectors.md) · [multitenancy (source)](https://github.com/qdrant/landing_page/blob/master/qdrant-landing/content/documentation/manage-data/multitenancy.md) · [quantization](https://qdrant.tech/documentation/manage-data/quantization/) · [binary quantization](https://qdrant.tech/articles/binary-quantization/) · [strict mode / administration](https://qdrant.tech/documentation/ops-configuration/administration/) · [hybrid search guide](https://qdrant.tech/articles/hybrid-search/) · [miniCOIL](https://qdrant.tech/articles/minicoil/) · [ColPali optimisation](https://qdrant.tech/blog/colpali-qdrant-optimization/) · [PDF retrieval at scale](https://qdrant.tech/documentation/tutorials-search-engineering/pdf-retrieval-at-scale/) · [fastembed](https://github.com/qdrant/fastembed) · [fastembed releases](https://github.com/qdrant/fastembed/releases)
- NVIDIA: [RAG blueprint](https://github.com/NVIDIA-AI-Blueprints/rag) · [2.5.0 release notes](https://docs.nvidia.com/rag/2.5.0/release-notes.html) · [nv-ingest](https://github.com/NVIDIA/nv-ingest) · [embed NIM card](https://docs.api.nvidia.com/nim/reference/nvidia-llama-nemotron-embed-1b-v2) · [rerank NIM card](https://docs.api.nvidia.com/nim/reference/nvidia-llama-nemotron-rerank-1b-v2) · [rerank NIM support matrix](https://docs.nvidia.com/nim/nemo-retriever/text-reranking/latest/support-matrix.html)
- Frameworks: [LlamaIndex releases](https://github.com/run-llama/llama_index/releases) · [LlamaIndex newsletter 2026-02-24](https://www.llamaindex.ai/blog/llamaindex-newsletter-2026-02-24) · [LangChain 1.0](https://www.langchain.com/blog/langchain-langgraph-1dot0) · [LangChain releases](https://github.com/langchain-ai/langchain/releases) · [Haystack 3.0.0](https://github.com/deepset-ai/haystack/releases/tag/v3.0.0) · [Haystack releases](https://github.com/deepset-ai/haystack/releases) · [DSPy releases](https://github.com/stanfordnlp/dspy/releases) · [RAGFlow](https://github.com/infiniflow/ragflow) · [Dify Knowledge Pipeline](https://dify.ai/blog/introducing-knowledge-pipeline) · [R2R](https://github.com/SciPhi-AI/r2r) · [Morphik](https://github.com/morphik-org/morphik-core) · [Kotaemon releases](https://github.com/Cinnamon/kotaemon/releases) · [Cognita](https://github.com/truefoundry/cognita) · [txtai releases](https://github.com/neuml/txtai/releases) · [Onyx licensing](https://wz-it.com/en/blog/onyx-self-hosted-installation/) · [Verba releases](https://github.com/weaviate/Verba/releases) · [ragbits](https://github.com/deepsense-ai/ragbits) · [Open WebUI RAG](https://docs.openwebui.com/features/chat-conversations/rag/) · [Open WebUI license](https://docs.openwebui.com/license/) · [AnythingLLM review](https://aifoss.dev/blog/anythingllm-review-2026/) · [GraphRAG releases](https://github.com/microsoft/graphrag/releases) · [GraphRAG query overview](https://github.com/microsoft/graphrag/blob/main/docs/query/overview.md) · [GraphRAG index methods](https://github.com/microsoft/graphrag/blob/main/docs/index/methods.md) · [LazyGraphRAG](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/) · [LightRAG](https://github.com/HKUDS/LightRAG) · [HippoRAG](https://github.com/OSU-NLP-Group/HippoRAG) · [PathRAG](https://github.com/BUPT-GAMMA/PathRAG) · [nano-graphrag](https://github.com/gusye1234/nano-graphrag) · [kernel-memory](https://github.com/microsoft/kernel-memory)
- Papers / evidence: [Anthropic contextual retrieval](https://www.anthropic.com/news/contextual-retrieval) · [Late chunking 2409.04701](https://arxiv.org/html/2409.04701v3) · [Dense X 2312.06648](https://arxiv.org/pdf/2312.06648) · [Semantic chunking 2410.13070](https://arxiv.org/html/2410.13070v1) · [RAPTOR](https://proceedings.iclr.cc/paper_files/paper/2024/hash/8a2acd174940dbca361a6398a4f9df91-Abstract-Conference.html) · [HyDE (Elastic case)](https://www.elastic.co/search-labs/blog/hyde-semantic-search-elasticsearch) · [Multi-query fusion study 2603.02153](https://arxiv.org/abs/2603.02153v1) · [Step-back 2310.06117](https://arxiv.org/abs/2310.06117v1) · [Self-RAG 2310.11511](https://arxiv.org/abs/2310.11511v1) · [CRAG 2401.15884](https://arxiv.org/html/2401.15884v3) · [Adaptive-RAG](https://aclanthology.org/2024.naacl-long.389) · [Agentic RAG survey 2501.09136](https://arxiv.org/abs/2501.09136) · [ColBERTv2 2112.01488](https://arxiv.org/pdf/2112.01488) · [ColPali 2407.01449](https://arxiv.org/pdf/2407.01449) · [ViDoRe v2](https://huggingface.co/blog/manu/vidore-v2) · [Nemotron ColEmbed V2 2602.03992](https://arxiv.org/pdf/2602.03992) · [Querit reranker benchmark 2606.19037](https://arxiv.org/pdf/2606.19037) · [Reranker comparison (ianas)](https://ianas.fr/en/blog/2026/06/07/reranker-comparatif-cohere-bge-jina-voyage/) · [RankZephyr 2312.02724](https://arxiv.org/abs/2312.02724v1) · [GraphRAG-Bench 2506.05690](https://www.alphaxiv.org/abs/2506.05690) · [RAG vs GraphRAG 2502.11371](https://arxiv.org/pdf/2502.11371) · [RAGU 2607.11683](https://arxiv.org/pdf/2607.11683) · [HippoRAG 2 2502.14802](https://arxiv.org/pdf/2502.14802) · [BRIGHT 2407.12883](https://arxiv.org/abs/2407.12883) · [MM-BRIGHT 2601.09562](https://arxiv.org/abs/2601.09562) · [FRAMES 2409.12941](https://alphaxiv.org/overview/2409.12941v3) · [RAGBench 2407.11005](https://arxiv.org/pdf/2407.11005)
- Embeddings / parsing: [premai 2026 embedding ranking](https://www.premai.io/blog/best-embedding-models-for-rag-2026-ranked-by-mteb-score-cost-and-self-hosting/) · [bentoml embedding guide](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models) · [Qwen3-Embedding-4B card](https://huggingface.co/Qwen/Qwen3-Embedding-4B) · [jina v4](https://jina.ai/models/jina-embeddings-v4/) · [bge-m3 (NVIDIA card)](https://build.nvidia.com/baai/bge-m3/modelcard) · [Docling releases](https://github.com/docling-project/docling/releases) · [Docling chunking (source)](https://github.com/docling-project/docling/blob/main/docs/concepts/chunking.md) · [MinerU](https://github.com/opendatalab/MinerU) · [Marker](https://github.com/datalab-to/marker) · [PyMuPDF RAG](https://github.com/pymupdf/RAG) · [unstructured](https://github.com/Unstructured-IO/unstructured) · [PDF parser comparison 2026](https://dev.to/moksh/pdf-parsers-for-rag-in-2026-when-open-weights-beat-the-frontier-models-4o9n) · [9-tool PDF benchmark](https://github.com/pdfmarkdownapp/pdf-to-markdown-benchmark) · [Reducto r-1](https://runtimewire.com/article/reducto-r1-document-parser-one-cent-page)
- Evaluation: [RAGAS metrics (source)](https://github.com/vibrantlabsai/ragas/blob/main/docs/concepts/metrics/available_metrics/index.md) · [DeepEval](https://github.com/confident-ai/deepeval) · [Phoenix](https://github.com/Arize-ai/phoenix) · [Langfuse](https://github.com/langfuse/langfuse) · [TruLens](https://github.com/truera/trulens) · [ARES](https://github.com/stanford-futuredata/ARES) · [eval tool comparison](https://futureagi.com/blog/best-rag-evaluation-tools-2026/)
