# Managed knowledge-retrieval / RAG platforms — market survey (as of 2026-10-16)

Purpose: inform the design of a pluggable retrieval engine that can later delegate to hosted backends.
Method: WebSearch (extended) + fetches of official docs where the sandbox allowed it (platform.claude.com, github.com, pypi.org were reachable; learn.microsoft.com, docs.aws.amazon.com, docs.cloud.google.com, platform.openai.com, docs.cohere.com, build.nvidia.com, docs.pinecone.io etc. were DNS-blocked from this sandbox, so those facts come from search-engine extracts of the official pages plus secondary sources). Every claim carries a URL and, where known, the date of the source. Items marked **[unverified]** could not be confirmed on a primary page and should be re-checked before budgeting or coding against them.

---

## 1. Microsoft Foundry IQ / Azure AI Search agentic retrieval (knowledge bases + knowledge sources)

**One line.** Foundry IQ is Microsoft's managed "knowledge layer" for agents; it is a thin product wrapper over Azure AI Search *knowledge bases*, which run *agentic retrieval* (LLM query planning → parallel sub-queries over one or more *knowledge sources* → semantic reranking → extractive or synthesized answer) and are exposed as REST and as an MCP server.
Sources: [What is Foundry IQ (Learn)](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/what-is-foundry-iq), [Foundry IQ FAQ (Learn)](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/foundry-iq-faq), [Agentic retrieval overview (Learn)](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview), [Foundry IQ announcement, Nov 2025](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/foundry-iq-unlocking-ubiquitous-knowledge-for-agents/4470812).

### Core concepts
- **Knowledge source** — a connection to data. Two families ([Knowledge source overview](https://learn.microsoft.com/en-us/azure/search/agentic-knowledge-source-overview); [Foundry IQ FAQ](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/foundry-iq-faq)):
  - *Indexed* (ingested into a search index via built-in indexer + skillset): existing **search index** (`searchIndex`), **Azure Blob Storage** (`azureBlob`, ADLS Gen2 ACL ingestion via `ingestionPermissionOptions`, preview), **OneLake** (`oneLake`), **SharePoint (indexed)**. Blob/OneLake/searchIndex are GA in REST `2026-04-01` ([What's new](https://learn.microsoft.com/en-us/azure/search/whats-new), April 2026 entry; [dev.to summary, 2026](https://dev.to/carlosjcastrog/foundry-iq-the-knowledge-layer-that-stops-every-agent-from-rebuilding-its-own-rag-1h46)).
  - *Remote / federated* (queried live at retrieval time, nothing copied): **SharePoint (remote)** via the Microsoft 365 Copilot Retrieval API (requires end-user Copilot license; user identity passed with `x-ms-query-source-authorization` so SharePoint trims results), **Web** via Grounding with Bing, and **MCP server** knowledge sources ([Create MCP knowledge source](https://learn.microsoft.com/en-us/azure/search/agentic-knowledge-source-how-to-mcp-server); [microsoft/azure-ai-search-foundry-iq-live-knowledge-sources repo](https://github.com/microsoft/azure-ai-search-foundry-iq-live-knowledge-sources/blob/main/docs/03-mcp-server-ks.md)). Remote kinds are preview in `2026-05-01-preview` / `2026-08-01-preview` and carry separate charges ([FAQ](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/foundry-iq-faq)).
- **Knowledge base** (renamed from "knowledge agent" in `2025-11-01-preview`; [migration guide](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-how-to-migrate)) — bundles **up to 10 knowledge sources** (tier-dependent; Basic 5–10, S1–L2 10) plus retrieval settings: `models` (Azure OpenAI chat deployment used for planning/synthesis), `retrievalInstructions`, `retrievalReasoningEffort` (`minimal` | `low` (default) | `medium`), `outputMode` (`extractiveData` | `answerSynthesis`) ([Create a knowledge base](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-how-to-create-knowledge-base); [Service limits](https://learn.microsoft.com/en-us/azure/search/search-limits-quotas-capacity); [Set reasoning effort](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-how-to-set-retrieval-reasoning-effort)).
- **Reasoning effort semantics** ([Service limits](https://learn.microsoft.com/en-us/azure/search/search-limits-quotas-capacity), fetched via search 2026-10):
  - `minimal`: no LLM query planning; fans the query to all sources; extractive only. This is the only mode in GA `2026-04-01`.
  - `low` (default): one LLM planning pass, decomposes into sub-queries, selects sources (≤3 on older preview tables), semantic ranker over ≤50 docs.
  - `medium`: deeper, iterative search ("agentic reasoning": re-plans if results are weak), selects ≤5 sources.
- **GA status**: knowledge bases + extractive retrieval + indexed source kinds are GA in REST `2026-04-01` (April 2026). Query planning, answer synthesis, configurable effort, multi-turn `messages`, remote sources, MCP endpoint and streaming are preview (`2026-08-01-preview` is current) ([What's new](https://learn.microsoft.com/en-us/azure/search/whats-new); [Query knowledge base via API or MCP](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-how-to-retrieve)). Portals are preview-only.

### API shape
Management (data-plane REST, bearer token or API key):
```
PUT  {endpoint}/knowledgesources('{name}')?api-version=2026-08-01-preview
PUT  {endpoint}/knowledgebases('{name}')?api-version=2026-08-01-preview
GET  {endpoint}/knowledgebases?api-version=...
```
Knowledge base body (abridged, from the Learn how-to):
```json
{
  "name": "earth-kb",
  "knowledgeSources": [{ "name": "earth-blob-ks" }, { "name": "earth-web-ks" }],
  "models": [{ "kind": "azureOpenAI",
               "azureOpenAIParameters": { "resourceUri": "https://x.openai.azure.com",
                                          "deploymentId": "gpt-4.1-mini", "modelName": "gpt-4.1-mini" } }],
  "retrievalInstructions": "Prefer the blob source for policy questions",
  "retrievalReasoningEffort": { "kind": "low" },
  "outputMode": "extractiveData"
}
```
Retrieve ([REST reference 2026-04-01](https://learn.microsoft.com/en-us/rest/api/searchservice/knowledge-retrieval/retrieve?view=rest-searchservice-2026-04-01); [how-to](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-how-to-retrieve)):
```
POST {endpoint}/knowledgebases('{name}')/retrieve?api-version=2026-08-01-preview
{
  "messages": [
    { "role": "assistant", "content": [{ "type": "text", "text": "<system-ish instructions>" }] },
    { "role": "user",      "content": [{ "type": "text", "text": "Why is the sky blue?" }] }
  ],
  "retrievalReasoningEffort": { "kind": "low" },      // overrides KB default (preview)
  "outputMode": "answerSynthesis",                     // or "extractiveData"
  "includeActivity": true, "includeReferences": true,
  "knowledgeSourceParams": [{ "kind": "searchIndex", "knowledgeSourceName": "earth-idx",
                              "filterAddOn": "category eq 'science'", "includeReferenceSourceData": true }],
  "maxRuntimeInSeconds": 30, "maxOutputSize": 5000
}
```
Response (200, or 206 partial when runtime/size cap hit):
```json
{
  "response":   [{ "content": [{ "type": "text", "text": "<extractive JSON-array of chunks | synthesized answer>" }] }],
  "activity":   [{ "type": "modelQueryPlanning", "id": 0, "inputTokens": 1300, "outputTokens": 80 },
                 { "type": "searchIndex", "id": 1, "knowledgeSourceName": "earth-idx",
                   "searchIndexArguments": { "search": "why sky blue rayleigh", "filter": null }, "count": 12, "elapsedMs": 140 },
                 { "type": "agenticReasoning", "id": 2, "..." : "..." },
                 { "type": "modelAnswerSynthesis", "id": 3, "inputTokens": 4000, "outputTokens": 200 }],
  "references": [{ "type": "searchIndex", "id": "0", "activitySource": 1, "docKey": "doc_17",
                   "rerankerScore": 3.5, "sourceData": { "chunk": "...", "title": "..." } }]
}
```
The extractive `response.text` is itself a JSON string: an array of `{ref_id, title, terms, content}` objects meant to be dropped straight into an LLM prompt ([quickstart](https://learn.microsoft.com/en-us/azure/search/search-get-started-agentic-retrieval)). Streaming (SSE, `answer.completed` event) arrives with `2026-08-01-preview` ([answer synthesis how-to](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-how-to-answer-synthesis)).

**MCP endpoint** (preview): every knowledge base is also an MCP server at
`https://<service>.search.windows.net/knowledgebases/<kb>/mcp?api-version=2026-08-01-preview`, bearer-token auth (Entra), exposing one tool `knowledge_base_retrieve`. Foundry Agent Service and Microsoft Agent Framework attach it as an MCP tool with `allowed_tools=["knowledge_base_retrieve"]` ([Query via API or MCP](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-how-to-retrieve); [Connect agents to Foundry IQ](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/foundry-iq-connect); [Agent Framework integration blog](https://devblogs.microsoft.com/foundry/foundry-iq-agent-framework-integration/)).

### What it does internally
LLM query planning (decomposition into sub-queries, source selection, optional iterative re-planning at `medium`), parallel execution of sub-queries against each source (hybrid vector+keyword for indexed sources; live calls for remote), semantic reranking (L2 cross-encoder, "L3" classification variant), merge, then either extractive packaging or LLM answer synthesis with citations. Microsoft claims up to 36% relevance gain over classic RAG (vendor-reported) ([blog, 2025-11](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/foundry-iq-boost-response-relevance-by-36-with-agentic-retrieval/4470720)).

### What it abstracts away / does NOT do
- Abstracts: ingestion + chunking + embedding (via indexer/skillset for Blob/OneLake/SharePoint), query decomposition, hybrid search, reranking, result packaging, ACL trimming for SharePoint/ADLS, MCP exposure.
- Does not: bring your own embedding/reranker models (Azure OpenAI only for planning/synthesis); no GraphRAG; no SQL/structured retrieval; remote Web source is Bing (not your own crawler); requires an Azure AI Search resource (Basic+ for knowledge bases, Free tier excluded).

### Pricing
Two bills ([Agentic retrieval overview](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview); [Pricing page](https://azure.microsoft.com/en-us/pricing/details/search/)):
1. Azure AI Search: *retrieval tokens* consumed by sub-query execution + semantic ranking, billed per 1M tokens, with a free monthly allowance of **50M tokens**; per-tier rates for Min/Low/Medium did not render in the fetched page **[unverified exact $]**. "Standard agentic retrieval plan" required for Foundry IQ.
2. Azure OpenAI: input/output tokens for planning + synthesis on the deployment you attach.
   Remote SharePoint and Web sources incur separate charges. A docs cost example lands at ≈$4.32 for 2,000 retrievals with gpt-4o-mini ([third-party summary](https://jannikreinhard.com/foundry-iq-knowledge-bases/)).

### Hard limits (from [Service limits](https://learn.microsoft.com/en-us/azure/search/search-limits-quotas-capacity))
≤10 knowledge sources per KB (S-tiers), ≤3 selected at `low`, ≤5 at `medium` (older table; current page says selection limits only); semantic ranker on ≤50 docs per sub-query at `low`; `maxRuntimeInSeconds`/`maxOutputSize` request caps (206 on overflow); messages input is preview-only.

### SDKs
- Python `azure-search-documents` **12.0.0** (PyPI 2026-05-01, targets REST `2026-04-01`): `azure.search.documents.knowledgebases.KnowledgeBaseRetrievalClient(endpoint, knowledge_base_name, credential).retrieve(KnowledgeBaseRetrievalRequest(messages=[...], knowledge_source_params=[SearchIndexKnowledgeSourceParams(...)]))`; models `KnowledgeBase`, `AzureBlobKnowledgeSource`, `SearchIndexKnowledgeSource`, `OneLakeKnowledgeSource`, `WebKnowledgeSource`; SharePoint kinds were removed from the GA package and live in previews ([PyPI](https://pypi.org/project/azure-search-documents/)). Preview surface requires `azure-search-documents` ≥ `2026-05-01-preview` betas plus `azure-ai-projects` ≥ 2.0.0 for Foundry agents ([dev.to](https://dev.to/carlosjcastrog/foundry-iq-the-knowledge-layer-that-stops-every-agent-from-rebuilding-its-own-rag-1h46)).
- .NET/JS/Java equivalents (`Azure.Search.Documents`, `@azure/search-documents`).

### How we would plug it in
Treat a knowledge base as a *retriever* backend: our engine's `retrieve(query, filters, top_k)` maps to one `POST .../retrieve` with `outputMode: extractiveData`, `retrievalReasoningEffort: minimal` (GA, cheapest, deterministic) or `low` (lets Azure do decomposition), `knowledgeSourceParams[].filterAddOn` for tenant/ACL filters, and `includeReferences: true`. Parse `references[]` (docKey, rerankerScore, sourceData) into our chunk schema and keep `activity[]` as a trace. For agent frameworks that already speak MCP, we can alternatively just register the KB's `/mcp` URL. Ingestion stays Azure-side (Blob/OneLake indexers); for data we chunk ourselves we push to a search index and wrap it as a `searchIndex` knowledge source.

---

## 2. Amazon Bedrock Knowledge Bases (customer-managed + the new Managed Knowledge Base)

**One line.** Bedrock Knowledge Bases is AWS's hosted RAG: you either bring a vector store ("customer-managed"/custom) or, since June 2026, use the fully managed index ("Managed Knowledge Base"), then query with `Retrieve`, `RetrieveAndGenerate`, or (managed only) `AgenticRetrieveStream`.
Sources: [AWS What's New, June 2026 — Managed KB GA](https://aws.amazon.com/about-aws/whats-new/2026/06/amazon-bedrock-managed-knowledge-base/), [AWS News blog](https://aws.amazon.com/blogs/aws/introducing-amazon-bedrock-managed-knowledge-base-for-faster-more-accurate-enterprise-ai-applications/), [Knowledge base user guide](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html).

### Core concepts
- **Knowledge base types** (2026):
  - *Managed* (GA 2026-06-17 per [AWS Builder article](https://builder.aws.com/content/3GSHEqVSuzVR0d8x4TJh2RWsXaE/amazon-bedrock-managed-knowledge-base-a-developers-take)): AWS-owned index; six native connectors (S3, SharePoint, Confluence, Google Drive, OneDrive, Web Crawler); bundled multimodal parser, managed embedding model, hybrid search and managed reranker "included at no extra cost"; document-level ACL filtering at retrieval (except Web Crawler); agentic retrieval. Loses: choice of vector store, GraphRAG, third-party connectors, `RetrieveAndGenerate`.
  - *Custom / customer-managed*: you pick the vector store — OpenSearch Serverless (default), OpenSearch managed, Aurora PostgreSQL pgvector, Neptune Analytics (GraphRAG), **S3 Vectors**, Pinecone, MongoDB Atlas, Redis Enterprise Cloud ([re:Post](https://repost.aws/questions/QUf3kvqg40QjKl-O_bGN-7mQ/s3-vectors-in-bedrock-knowledge-base); [architecture guide, 2026](https://hidekazu-konishi.com/entry/amazon_bedrock_rag_architecture_guide.html)); embedding models Titan Text Embeddings v2, Cohere Embed v3/v4, Nova Multimodal Embeddings (text ≤8,172 tokens, video/audio segments) ([multimodal blog](https://aws.amazon.com/blogs/machine-learning/introducing-multimodal-retrieval-for-amazon-bedrock-knowledge-bases/)); parsers: default, **Bedrock Data Automation** (BDA), foundation-model parser; chunking: fixed, semantic (20–8,192 tokens), hierarchical (parent ≤8,192), custom Lambda ([advanced parsing blog](https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-knowledge-bases-now-supports-advanced-parsing-chunking-and-query-reformulation-giving-greater-control-of-accuracy-in-rag-based-applications/)).
- **GraphRAG** (GA March 2025): Neptune Analytics stores embeddings + an entity/relationship graph; S3 source only; 1,000 files/data source default ([What's New 2025-03](https://aws.amazon.com/about-aws/whats-new/2025/03/amazon-bedrock-knowledge-bases-graphrag-generally-available)).
- **Structured data retrieval**: KB over Redshift / Glue (SageMaker Lakehouse) that generates SQL at query time (`GenerateQuery` API; `content.row` results) **[GenerateQuery name not re-verified this pass]**.
- **Reranking**: `Rerank` API (Dec 2024) with Amazon Rerank 1.0 and Cohere Rerank 3.5; wired into Retrieve via `rerankingConfiguration` ([What's New 2024-12](https://aws.amazon.com/about-aws/whats-new/2024/12/amazon-bedrock-rerank-api-accuracy-rag-applications)).
- **Agentic retrieval** (managed KBs only, `bedrock:AgenticRetrieveStream`): planner model decomposes into sub-queries, retrieves per sub-query, judges sufficiency, loops ≤`maxAgentIteration` (min 2, default 5 per blog) with a "SpeculativeRetrieval" step that doesn't count ([Use agentic retrieval](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-agentic-retrieve.html); [AgenticRetrieveConfiguration](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_AgenticRetrieveConfiguration.html); [AWS ML blog](https://aws.amazon.com/blogs/machine-learning/agentic-retrieval-for-amazon-bedrock-managed-knowledge-base/)).
- **MCP**: AgentCore Gateway can expose a managed KB as an MCP target with two tools (plain retrieve + `AgenticRetrieveStream`) ([Connect through AgentCore Gateway](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-gateway-target.html)).

### API shape (`bedrock-agent-runtime`, [Retrieve reference](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_Retrieve.html); [boto3 retrieve](https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock-agent-runtime/client/retrieve.html))
```
POST /knowledgebases/{knowledgeBaseId}/retrieve
{
  "retrievalQuery": { "text": "What is the refund policy?" },
  "retrievalConfiguration": {
    "vectorSearchConfiguration": {            // custom KBs only
      "numberOfResults": 10,
      "overrideSearchType": "HYBRID" | "SEMANTIC",
      "filter": { "equals": { "key": "tenant", "value": "acme" } },
      "rerankingConfiguration": { "type": "BEDROCK_RERANKING_MODEL",
        "bedrockRerankingConfiguration": { "modelConfiguration": { "modelArn": "arn:...cohere.rerank-v3-5:0" }, "numberOfRerankedResults": 5 } },
      "implicitFilterConfiguration": { "metadataAttributes": [...], "modelArn": "..." }
    }
    /* managed KBs instead use:
    "managedSearchConfiguration": { "numberOfResults": 10, "filter": {...},
      "rerankingConfiguration": { "rerankingModelType": "NONE"|"CUSTOM" } } */
  },
  "userContext": { "filters": [...] },         // ACL trimming for managed KBs
  "guardrailConfiguration": { "guardrailId": "...", "guardrailVersion": "1" },
  "nextToken": "..."
}
→ { "retrievalResults": [ { "content": { "type": "TEXT"|"IMAGE"|"ROW", "text": "...", "byteContent": "...", "row": [...] },
                            "location": { "type": "S3"|"WEB"|"CONFLUENCE"|"SALESFORCE"|"SHAREPOINT"|"CUSTOM"|"KENDRA"|"SQL"|"ONEDRIVE"|"GOOGLEDRIVE",
                                          "s3Location": { "uri": "s3://..." } },
                            "metadata": { "x-amz-bedrock-kb-source-uri": "...", "tenant": "acme" },
                            "score": 0.73 } ],
    "guardrailAction": "NONE", "nextToken": null }
```
`RetrieveAndGenerate` ([reference](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_RetrieveAndGenerate.html)): `{ input:{text}, retrieveAndGenerateConfiguration:{ type:"KNOWLEDGE_BASE", knowledgeBaseConfiguration:{ knowledgeBaseId, modelArn, retrievalConfiguration:{...}, generationConfiguration:{ promptTemplate, inferenceConfig, guardrailConfiguration }, orchestrationConfiguration:{ queryTransformationConfiguration:{type:"QUERY_DECOMPOSITION"} } } }, sessionId }` → `{ output:{text}, citations:[{ generatedResponsePart:{textResponsePart:{span:{start,end},text}}, retrievedReferences:[{content,location,metadata}] }], sessionId, guardrailAction }`. Not usable with managed KBs ([re:Post](https://repost.aws/questions/QU58qnvOYPSTSRwKqo9cgXNQ/bedrock-agent-fails-when-querying-attached-managed-knowledge-base-with-error-vectorsearchconfiguration-is-not-supported-for-managed-knowledge-bases)).
`AgenticRetrieveStream` ([boto3](https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock-agent-runtime/client/agentic_retrieve_stream.html)): `{ messages:[{role,content}], retrievers:[{ knowledgeBaseConfiguration:{ knowledgeBaseId, filter } }], agenticRetrieveConfiguration:{ foundationModelConfiguration:{ foundationModelType:"BEDROCK"|"MANTLE", modelArn }, maxAgentIteration:5, rerankingConfiguration }, generateResponse:true, sessionId }` → event stream of trace / retrieval-result / text chunks. LangChain wrapper: `langchain_aws.retrievers.agentic_retrieve` (langchain-aws ≥1.6.3) ([LangChain docs](https://docs.langchain.com/oss/python/integrations/retrievers/bedrock)).

### What it abstracts / does NOT do
- Abstracts (managed): connectors, parsing (multimodal), chunking, embedding, hybrid index, rerank, ACL filtering, agentic decomposition, MCP via AgentCore.
- Does not: expose the embedding vectors (managed) or let you choose models (managed); custom KB requires you to provision/pay the vector store; GraphRAG only with Neptune + S3; no built-in web-search federation; `RetrieveAndGenerate` ≠ managed.

### Pricing ([Bedrock pricing](https://aws.amazon.com/bedrock/pricing/); [agentic retrieval blog](https://aws.amazon.com/blogs/machine-learning/agentic-retrieval-for-amazon-bedrock-managed-knowledge-base/); third-party roll-ups [cloudzero](https://www.cloudzero.com/blog/amazon-bedrock-pricing/), [caylent](https://caylent.com/blog/amazon-bedrock-pricing-explained))
- Managed KB: **$5 / GB-month** raw indexed data; **$1 / 1,000 Retrieve calls**; agentic retrieval **$4 / 1,000 agentic calls + $1 / 1,000 underlying Retrieve calls** (plus FM tokens if you choose a non-managed planner); parser/embeddings/reranker shown as "Included".
- Custom KB: pay the vector store (OpenSearch Serverless OCUs, Aurora, S3 Vectors…), embedding model tokens, BDA parsing **$0.010/page** (standard output), FM parser tokens, Rerank models **$1/1k queries (Amazon Rerank 1.0), $2/1k (Cohere Rerank 3.5)** [third-party], structured SQL generation **≈$2 / 1,000 queries** [third-party, ~300 days old].

### Limits ([managed quotas](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-quotas.html); [data prerequisites](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-ds.html))
200 data sources per managed KB (not adjustable); 10 TB raw per managed KB; 50 MB per file (3.75 MB JPEG/PNG), 10 KB metadata sidecar; 600 Retrieve RPM per KB (burst 25 RPS, adjustable); 5 concurrent ingestion jobs/account; `maxAgentIteration` ≥2; `numberOfResults` max 100 **[unverified this pass]**.

### SDK
boto3 `bedrock-agent` (control plane: `create_knowledge_base`, `create_data_source`, `start_ingestion_job`) and `bedrock-agent-runtime` (`retrieve`, `retrieve_and_generate`, `retrieve_and_generate_stream`, `agentic_retrieve_stream`, `rerank`). `AgenticRetrieveStream` not yet in AWS CLI (re:Post).

### How we would plug it in
Map our `retrieve()` to `bedrock-agent-runtime.retrieve` with `retrievalConfiguration.{vectorSearchConfiguration|managedSearchConfiguration}` chosen by KB type (detect via `bedrock-agent.get_knowledge_base`); pass tenant filters through `filter` (custom) or `userContext.filters` (managed ACL); normalize `retrievalResults[]` → `{text|bytes|row, uri (from location.*), score, metadata}`. Offer an "agentic" mode that streams `agentic_retrieve_stream` and collects retrieval events for multi-hop questions. Reranking can be Bedrock-side (`rerankingConfiguration`) or ours. For managed KBs we can also skip boto3 entirely and treat the AgentCore Gateway MCP target as the transport.

---

## 3. Google Vertex AI RAG Engine and Vertex AI Search (now "Agent Search" under "Gemini Enterprise Agent Platform")

**One line.** RAG Engine is a managed corpus→chunk→embed→retrieve service (`retrieveContexts`) that also plugs into Gemini as a `retrieval.vertex_rag_store` tool; Vertex AI Search / Agent Search is the enterprise search product (Discovery Engine API: `servingConfigs:search` / `:answer`) usable standalone or as the `vertex_ai_search` grounding tool.
Naming: Google announced "Gemini Enterprise Agent Platform" as the evolution of Vertex AI on 2026-04-22 ([Wikipedia](https://en.wikipedia.org/wiki/Gemini_Enterprise_Agent_Platform)); docs now say "Vertex AI Search is being renamed to Agent Search" ([REST reference](https://cloud.google.com/generative-ai-app-builder/docs/reference/rest/v1/projects.locations.collections.dataStores.servingConfigs/search)).

### 3a. Vertex AI RAG Engine
- **Concepts** ([RAG Engine API](https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/rag-api); [vector DB choices](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/rag-engine/vector-db-choices)): `RagCorpus` (per-location resource with an embedding model config and a backend: **RagManagedDb** default (Spanner-backed; tiers Basic=100 PU, Scaled=1–10 nodes autoscale, Unprovisioned=deleted), Vertex Vector Search, Pinecone, Weaviate, Feature Store), `RagFile` (imported from GCS, Google Drive, Slack, Jira, or uploaded), chunking (`fixed_length_chunking` + overlap), parsers (default, layout parser via Document AI, LLM parser), `RagRetrievalConfig`. **Serverless mode** (public preview, April 2026) removes Spanner provisioning; **cross-corpus retrieval** preview (April 2026) ([Vertex release notes](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/release-notes); [Releasebot](https://releasebot.io/updates/google/vertex-ai)). Schema-based metadata filtering on corpora added Dec 2025.
- **API** (`aiplatform.googleapis.com/v1`, from [vertex_rag_service.proto](https://github.com/googleapis/googleapis/blob/master/google/cloud/aiplatform/v1/vertex_rag_service.proto) and [tool.proto](https://github.com/googleapis/googleapis/blob/master/google/cloud/aiplatform/v1/tool.proto), fetched 2026-10-16):
```
POST https://{region}-aiplatform.googleapis.com/v1/projects/{p}/locations/{l}:retrieveContexts
{
  "vertex_rag_store": { "rag_resources": [{ "rag_corpus": "projects/p/locations/l/ragCorpora/123",
                                            "rag_file_ids": ["..."] }] },
  "query": { "text": "What is our PTO policy?",
             "rag_retrieval_config": {
               "top_k": 10,
               "filter": { "vector_distance_threshold": 0.5,        // or vector_similarity_threshold
                           "metadata_filter": "department = \"HR\"" },
               "ranking": { "rank_service": { "model_name": "semantic-ranker-default@latest" } }
                          /* or "llm_ranker": { "model_name": "gemini-2.5-flash" } */ } } }
→ { "contexts": { "contexts": [ { "source_uri": "gs://bucket/pto.pdf", "source_display_name": "pto.pdf",
                                  "text": "...chunk...", "score": 0.23, "chunk": { "page_span": {...} } } ] } }
```
  `hybrid_search.alpha` applies only to Weaviate backends. Gemini tool form: `tools=[{ "retrieval": { "vertex_rag_store": { "rag_resources":[...], "rag_retrieval_config":{...} } } }]` in `generateContent`; responses carry `grounding_metadata.grounding_chunks[].retrieved_context{uri,title,text}` and `grounding_supports` (UTF-8 **byte** offsets, not chars — [blog warning](https://drpranayjha.com/vertex-ai-grounding-google-search/)). Also `augmentPrompt` and `corroborateContent` (claim-level citation scores with `citation_threshold`).
- **Pricing** ([RAG Engine billing](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/rag-engine/rag-engine-billing)): no per-call RAG Engine fee; you pay embedding tokens (ingest + query), the **Spanner instance behind RagManagedDb at standard Spanner rates every hour it exists** (since Sept 2025), LLM tokens for generation/LLM-ranker, Discovery Engine ranking API for `rank_service`, Document AI for layout parser. Fixed-size chunking and default parser are free. Community thread cites $2.50 / 1,000 grounded requests when used as a grounding source **[unverified]** ([forum](https://discuss.google.dev/t/vertex-ai-rag-engine-price-retrievecontexts/190665)).
- **Limits**: 10,000 files per import request, 3 concurrent imports/region, 600 retrieval RPM/region [third-party] ([guide](https://blog.lordpatil.com/posts/enterprise-rag-vertex-ai-rag-engine/)); only text queries; one corpus per `rag_resources` call (cross-corpus is preview).
- **SDK**: `google-cloud-aiplatform` — `from vertexai import rag; rag.create_corpus(...)`, `rag.import_files(...)`, `rag.retrieval_query(rag_resources=[...], text=..., rag_retrieval_config=rag.RagRetrievalConfig(top_k=..., filter=rag.Filter(vector_distance_threshold=...), ranking=rag.Ranking(rank_service=rag.RankService(model_name=...))))`; newer `google-genai` style `client.rag.create_corpus` appears in 2026 docs ([Use Vector Search with RAG Engine](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/rag-engine/use-vertexai-vector-search)); Terraform `google_vertex_ai_rag_engine_config`.

### 3b. Vertex AI Search / Agent Search (Discovery Engine)
- **Concepts**: data stores (unstructured docs, structured, website, connectors incl. SharePoint/Confluence/Jira/etc.), engines/apps, serving configs; Search Standard vs Enterprise editions; "Grounded Generation API"; `answer` method with query rephrasing, citations, grounding scores ([Builder APIs](https://docs.cloud.google.com/generative-ai-app-builder/docs/builder-apis); [Agent Search release notes](https://docs.cloud.google.com/generative-ai-app-builder/docs/release-notes)).
- **API** ([search method](https://cloud.google.com/generative-ai-app-builder/docs/reference/rest/v1/projects.locations.collections.dataStores.servingConfigs/search); [conversational_search_service.proto](https://github.com/googleapis/googleapis/blob/master/google/cloud/discoveryengine/v1/conversational_search_service.proto)):
```
POST https://discoveryengine.googleapis.com/v1/projects/{p}/locations/global/collections/default_collection/engines/{e}/servingConfigs/default_search:search
{ "query": "pto policy", "pageSize": 10, "filter": "department: ANY(\"HR\")",
  "contentSearchSpec": { "snippetSpec": { "returnSnippet": true },
                         "extractiveContentSpec": { "maxExtractiveAnswerCount": 1, "maxExtractiveSegmentCount": 3 },
                         "summarySpec": { "summaryResultCount": 5, "includeCitations": true } },
  "dataStoreSpecs": [...] }
→ { "results": [{ "document": { "id", "name", "derivedStructData": { "title", "link", "snippets": [...], "extractive_answers": [...] } } }],
    "summary": { "summaryText": "...", "summaryWithMetadata": { "citationMetadata": {...}, "references": [...] } }, "totalSize": 42 }

POST .../servingConfigs/default_search:answer
{ "query": { "text": "..." }, "session": "...", 
  "answerGenerationSpec": { "modelSpec": {"modelVersion": "stable"}, "promptSpec": {"preamble": "..."}, "includeCitations": true,
                            "ignoreAdversarialQuery": true, "ignoreNonAnswerSeekingQuery": true, "ignoreLowRelevantContent": true },
  "searchSpec": { "searchParams": { "maxReturnResults": 10, "filter": "...", "boostSpec": {...}, "searchResultMode": "CHUNKS", "dataStoreSpecs": [...] } },
  "queryUnderstandingSpec": { "queryRephraserSpec": { "maxRephraseSteps": 1 }, "queryClassificationSpec": { "types": [...] } },
  "groundingSpec": { "includeGroundingSupports": true, "filteringLevel": "..." } }
→ { "answer": { "answerText", "citations", "references", "steps", "queryUnderstandingInfo", "groundingScore" }, "session", "answerQueryToken" }
```
  Gemini grounding tool: `tools=[{ "retrieval": { "vertex_ai_search": { "datastore": "projects/.../dataStores/x" | "engine": "...", "max_results": 10, "filter": "...", "data_store_specs": [...] } } }]` (tool.proto).
- **Pricing** ([Agent Search pricing](https://cloud.google.com/generative-ai-app-builder/pricing); 2026 roll-ups [betterclaw](https://www.betterclaw.io/blog/google-vertex-ai-agent-builder), [costbench](https://costbench.com/software/rag-pipelines/vertex-ai-search/)): Search Standard **$1.50 / 1,000 queries**, Enterprise **$4.00 / 1,000 queries** (includes core generative answers; advanced answers extra); 10,000 free queries/month [third-party]; data index **$5 / GiB-month** (first 10 GiB free); Grounding with Google Search 5,000 free/month then **$14 / 1,000** (Gemini pricing page). Official page shown in results was stale (metadata ~1,300 days) — re-verify.
- **Limits/SDK**: `google-cloud-discoveryengine` Python (`SearchServiceClient.search`, `ConversationalSearchServiceClient.answer_query`); quotas per project (QPS) in console.

### What they abstract / do NOT do
RAG Engine abstracts chunking/embedding/vector store/reranking but not Spanner cost or generation; it does not do query decomposition (that's Gemini's job), GraphRAG, or ACLs. Agent Search abstracts crawling/connectors/ACLs (for connector data stores), hybrid search, rephrasing, answer+citations; it does not expose vectors or let you choose the embedding model, and its structured-data story is separate.

### How we would plug it in
Two adapters: (a) `RagEngineRetriever` → `retrieveContexts` with `rag_retrieval_config` (top_k, thresholds, metadata_filter, optional `rank_service`), normalizing `contexts[]` → chunks (score semantics depend on distance metric; invert cosine distance). (b) `AgentSearchRetriever` → `servingConfigs:search` with `searchResultMode: CHUNKS` + `extractiveContentSpec` for passage-level results, or `:answer` when we want Google to do rephrasing + citation; map `document.derivedStructData` and `citationMetadata` into our citation schema. Both can also be registered as Gemini `retrieval` tools when the generator is Gemini.

---

## 4. OpenAI Responses API `file_search` tool + Vector Stores API

**One line.** OpenAI hosts a chunk→embed→hybrid-search index ("vector store") that the Responses API can query automatically via the `file_search` tool, or that you can query directly with `POST /v1/vector_stores/{id}/search`.
Sources: [File search guide](https://developers.openai.com/api/docs/guides/tools-file-search), [Retrieval guide](https://platform.openai.com/docs/guides/retrieval), [Vector store search reference](https://developers.openai.com/api/reference/resources/vector_stores/methods/search), [openai-python types (fetched 2026-10-16)](https://github.com/openai/openai-python/blob/main/src/openai/types/responses/file_search_tool.py), [Pricing](https://platform.openai.com/docs/pricing/), [Responses API launch, Mar 2025](https://openai.com/index/new-tools-and-features-in-the-responses-api/).

### Core concepts
Files (`/v1/files`, purpose `assistants`) → **vector store** (`/v1/vector_stores`, `chunking_strategy`: `auto` = 800 max tokens / 400 overlap, or `static {max_chunk_size_tokens, chunk_overlap_tokens}`; `expires_after {anchor:"last_active_at", days}`; `metadata`) → vector store files/batches (each file may carry `attributes` ≤16 key/values for filtering) → search (hybrid semantic + keyword with reciprocal rank fusion, optional query rewrite, reranker `auto`/`default-2024-11-15`/`none`, `score_threshold`).

### API shape
Responses tool ([file_search_tool.py](https://github.com/openai/openai-python/blob/main/src/openai/types/responses/file_search_tool.py)):
```json
POST /v1/responses
{ "model": "gpt-5", "input": "What is our PTO policy?",
  "tools": [{ "type": "file_search", "vector_store_ids": ["vs_123"],
              "max_num_results": 10,                                   // 1..50
              "filters": { "type": "and", "filters": [ { "type": "eq", "key": "tenant", "value": "acme" } ] },
              "ranking_options": { "ranker": "auto", "score_threshold": 0.3,
                                   "hybrid_search": { "embedding_weight": 0.7, "text_weight": 0.3 } } }],
  "include": ["file_search_call.results"] }
→ output: [ { "type": "file_search_call", "id": "fs_1", "status": "completed"|"in_progress"|"searching"|"incomplete"|"failed",
              "queries": ["PTO policy"],
              "results": [ { "file_id": "file_9", "filename": "hr.pdf", "score": 0.81, "text": "...", "attributes": {"tenant":"acme"} } ] },
            { "type": "message", "content": [{ "type": "output_text", "text": "...",
              "annotations": [{ "type": "file_citation", "file_id": "file_9", "filename": "hr.pdf", "index": 120 }] }] } ]
```
Direct search ([vector_store_search_params.py](https://github.com/openai/openai-python/blob/main/src/openai/types/vector_store_search_params.py), [response](https://github.com/openai/openai-python/blob/main/src/openai/types/vector_store_search_response.py)):
```json
POST /v1/vector_stores/vs_123/search
{ "query": "PTO policy", "max_num_results": 10, "rewrite_query": true,
  "filters": { "type": "eq", "key": "tenant", "value": "acme" },
  "ranking_options": { "ranker": "auto", "score_threshold": 0.3 } }
→ { "object": "vector_store.search_results.page", "search_query": ["PTO policy"],
    "data": [ { "file_id": "file_9", "filename": "hr.pdf", "score": 0.81, "attributes": {...},
                "content": [ { "type": "text", "text": "..." } ] } ],
    "has_more": false, "next_page": null }
```

### What it abstracts / does NOT do
Abstracts parsing (PDF/DOCX/PPTX/code/text…), chunking, embedding (text-embedding-3-large), hybrid search, rerank, query rewrite, citations into the model output. Does not: expose embeddings, support image/audio content in stores, do ACLs beyond your own `attributes` filters, do query decomposition outside the model loop, support more than a handful of vector stores per request (docs historically: 1 store per tool call at a time — re-verify), or run outside OpenAI's models for the tool (direct search endpoint is model-agnostic).

### Pricing ([Pricing](https://platform.openai.com/docs/pricing/); confirmed same since Mar 2025 launch; 2026 roll-ups [eesel](https://www.eesel.ai/blog/openai-agents-api-pricing), [markaicode checked 2026-09-03](https://markaicode.com/pricing/openai-agents-sdk-pricing/))
Storage **$0.10 / GB / day** (first 1 GB free; billed on parsed chunks + embeddings, not raw file size); tool calls **$2.50 / 1,000 calls**; direct vector-store search endpoint reported to bill the same per-call rate [forum, unverified]. Embedding at ingest is not separately billed.

### Limits
512 MB and 5M tokens per file; 100 GB per project by default; **10,000 files per vector store** (hard, per support) ([forum](https://community.openai.com/t/increasing-the-number-of-files-in-the-file-search-vector-store/886686)); 300 RPM shared across vector-store file endpoints per store; `max_num_results` ≤50; `attributes` ≤16 pairs (keys ≤64 chars, values ≤512). Model context typically receives ~20 chunks × ≤800 tokens.

### SDK
`openai` Python/TS: `client.vector_stores.create/files.upload_and_poll/search`, `client.responses.create(tools=[{"type":"file_search",...}])`. Azure OpenAI exposes the same tool in Foundry.

### How we would plug it in
Use the **direct search endpoint** as the retriever (model-agnostic, returns chunk text + score + file attributes): `retrieve()` → `POST /vector_stores/{id}/search` with `rewrite_query`, `filters` built from our metadata, `ranking_options.score_threshold`. Map `data[]` → chunks keyed by `file_id` + ordinal; keep a sidecar of our doc ids in `attributes` at upload. Optionally, when the generator is an OpenAI model, let the `file_search` tool run in-loop and harvest `file_search_call.results` via `include`. Ingestion = upload file → add to store with `chunking_strategy.static` tuned to our chunk size.

---

## 5. NVIDIA NeMo Retriever, NIM microservices, and the NVIDIA RAG Blueprint

**One line.** Not a hosted knowledge base: a set of self-hostable (or build.nvidia.com-hosted) OpenAI-compatible microservices for embedding, reranking and document extraction, plus a reference RAG server (the "RAG Blueprint") you deploy yourself.
Sources: [RAG Blueprint repo README (fetched 2026-10-16)](https://github.com/NVIDIA-AI-Blueprints/rag), [release notes (fetched 2026-10-16)](https://github.com/NVIDIA-AI-Blueprints/rag/blob/main/docs/release-notes.md), [RAG server OpenAPI (fetched)](https://github.com/NVIDIA-AI-Blueprints/rag/blob/main/docs/api_reference/openapi_schema_rag_server.json), [NeMo Retriever](https://developer.nvidia.com/nemo-retriever), [NeMo Retriever extraction support matrix 26.5.0](https://docs.nvidia.com/nemo/retriever/26.5.0/extraction/prerequisites-support-matrix/).

### Latest version and components
- **RAG Blueprint v2.6.2 (2026-08-17)**; v2.6.1 (2026-08-06); **v2.6.0 (2026-05-30)** introduced *Agentic RAG* (LangGraph plan-and-execute, streaming, per-request `agentic: true`), switched the default vector DB from Milvus to **Elasticsearch** (cuVS-accelerated; Milvus optional), default object store MinIO→SeaweedFS, dynamic filter expressions, OpenShift Helm. v2.4.0 (2026-02-20) added an **MCP server**, an OpenAI-compatible `/v1/search` endpoint, weighted hybrid search, image+text query input, non-NIM model support, collection-level data catalog.
- Components: RAG orchestrator server (LangChain), NeMo Retriever Extraction / **NV-Ingest 26.3.0** (multimodal PDF/office/audio ingestion: text, tables, charts, infographics), vector DB, sample UI, optional NeMo Guardrails, telemetry, Python "library mode".
- **Default models in 2.6.x** (cloud/build.nvidia.com defaults): LLM `nvidia/nemotron-3-ultra-550b-a55b` (2.6.1; was `nemotron-3-super-120b-a12b`), embedding `nvidia/llama-nemotron-embed-vl-1b-v2` (VLM, default) with text-only `nvidia/llama-nemotron-embed-1b-v2` optional, reranker `nvidia/llama-nemotron-rerank-1b-v2` (on-prem) / `nvidia/llama-nemotron-rerank-vl-1b-v2` (cloud default from 2.6.2), extraction NIMs `nemotron-page-elements-v3`, `nemotron-table-structure-v1`, `nemotron-graphic-elements-v1`, OCR `nemotron-ocr-v1` (renamed from `nemoretriever-ocr-v1`; an OCR **v2** NIM container exists on NGC), VLM `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` (opt-in), `nemotron-parse` (Parse 1.1, 885M encoder-decoder; experimental parse-only pipeline), optional PaddleOCR, Riva ASR, NemoGuard safety/topic control. Migration guidance exists for `nemotron-3-embed-1b:2.2.1` (2048-dim, needs re-ingest).
- **Models on build.nvidia.com now** (search-verified): `nvidia/llama-3.2-nv-embedqa-1b-v2` (8,192 tokens, multilingual, Matryoshka dims) and `nvidia/llama-3.2-nv-rerankqa-1b-v2` (still listed; "3.5× smaller than nv-rerankqa-mistral-4b-v3") ([NIM reference](https://docs.api.nvidia.com/nim/reference/nvidia-llama-3_2-nv-embedqa-1b-v2)); `nvidia/llama-nemotron-embed-1b-v2`, `nvidia/llama-nemotron-rerank-1b-v2` (model card dated 2026-02-27), `nvidia/llama-nemotron-embed-vl-1b-v2`, `nvidia/llama-nemotron-rerank-vl-1b-v2`; **`nvidia/nemotron-3-embed-1b`** (July 2026 "Nemotron 3 Embed" family: 8B BF16 @4096-d, 1B BF16/NVFP4 @2048-d, 32,768 max tokens, OpenMDW-1.1 license, truncatable to 1024/512 with re-normalization) ([model card](https://build.nvidia.com/nvidia/nemotron-3-embed-1b/modelcard); [MarkTechPost 2026-07-17](https://www.marktechpost.com/2026/07/17/nvidia-ai-releases-nemotron-3-embed-an-open-embedding-collection-whose-8b-checkpoint-ranks-1-on-rteb/)); `nemotron-parse-2.0` (VLM document parser, updated 2026-09-15 per [build.nvidia.com/models](https://build.nvidia.com/models)) **[parse-2.0 seen only in one search extract]**; no "nemotron-3-rerank" found yet. Older `nv-rerankqa-mistral-4b-v3`, `nv-embedqa-e5-v5`, `llama-3.2-nemoretriever-1b-vlm-embed-v1` remain available/legacy.

### API shape
NIM embedding (OpenAI-compatible, [NeMo Retriever embedding NIM reference](https://docs.nvidia.com/nim/nemo-retriever/embedding/latest/use-the-api-openai.html)):
```json
POST {base}/v1/embeddings
{ "model": "nvidia/llama-nemotron-embed-1b-v2", "input": ["..."],
  "input_type": "query" | "passage",          // required for NV-Embed-QA/E5 family; wrong value = large accuracy drop
  "truncate": "NONE" | "START" | "END", "encoding_format": "float", "modality": "text" }
→ OpenAI embeddings shape. (OpenAI SDKs that reject input_type can use model suffix "-query"/"-passage".)
```
NIM reranking ([langchain-nvidia reranking.py, fetched](https://github.com/langchain-ai/langchain-nvidia/blob/main/libs/ai-endpoints/langchain_nvidia_ai_endpoints/reranking.py)):
```json
POST {base}/v1/ranking
{ "model": "nvidia/llama-nemotron-rerank-1b-v2", "query": { "text": "..." },
  "passages": [ { "text": "..." }, { "text": "...", "image": "<base64>" } ], "truncate": "END" }
→ { "rankings": [ { "index": 2, "logit": 3.1 }, { "index": 0, "logit": -1.2 } ] }
```
RAG Blueprint server ([OpenAPI, fetched](https://github.com/NVIDIA-AI-Blueprints/rag/blob/main/docs/api_reference/openapi_schema_rag_server.json)): `POST /v1/search` body `{ query: string | [{type:text|image_url,...}], collection_names:["multimodal_data"], reranker_top_k:10 (≤25), vdb_top_k:100 (≤400), enable_reranker:true, enable_query_rewriting:false, filter_expr:"" , enable_filter_generator:false, confidence_threshold:0, enable_citations:true, embedding_model, reranker_model, messages:[] }` → `{ total_results, results:[SourceResult{document_id, content, document_name, document_type, score, metadata}] }`; `POST /v1/generate` (`/v1/chat/completions` alias) with `use_knowledge_base`, `agentic`, same retrieval knobs; `POST /v1/documents` on the ingestor; `GET /v1/summary`. Hosted NIMs: `https://integrate.api.nvidia.com/v1`.

### What it abstracts / does NOT do
Abstracts model serving (TensorRT-optimized containers), multimodal extraction, and gives a reference orchestrator with hybrid search, rerank, query decomposition/rewriting, filter generation, citations, agentic loop. Does **not** host your data (you run Elasticsearch/Milvus, NV-Ingest, NIMs on GPUs or use NVIDIA-hosted model endpoints only), no ACL model, no connectors beyond file upload; GPU requirements are substantial (see `docs/deploy-docker-self-hosted.md`).

### Pricing
Software: Apache-2.0 blueprint; NIM containers require NVIDIA AI Enterprise license for production (free for dev via NGC). Hosted `integrate.api.nvidia.com` endpoints are free-tier/credits for experimentation (rate-limited); production = your GPUs or cloud GPU hours. No per-query list price **[no official $ found]**.

### Limits
`reranker_top_k` ≤25, `vdb_top_k` ≤400 (blueprint schema); embed context 8,192 tokens (llama-3.2 family) / 32,768 (Nemotron-3-Embed); reranker inputs truncated per `truncate`.

### SDK
OpenAI SDK (embeddings), `langchain-nvidia-ai-endpoints` (`NVIDIAEmbeddings`, `NVIDIARerank`), `nv-ingest-client`, `nvidia-rag` Python library mode; Helm charts `nvidia-blueprint-rag` and `nemo-retriever 26.08.1` on NGC.

### How we would plug it in
Two levels: (a) **model-level** — our engine's embedding and reranking provider interfaces get NIM implementations (`/v1/embeddings` with `input_type`, `/v1/ranking` with logits→scores), pointing at either hosted `integrate.api.nvidia.com` or a self-hosted NIM; NV-Ingest becomes an optional document parser producing text/table/chart chunks with page metadata. (b) **service-level** — a `NvidiaRagBlueprintRetriever` that calls `POST /v1/search` on a deployed blueprint and maps `results[]` (document_id, content, score, metadata) to our chunk schema, passing our metadata filters as `filter_expr`. The blueprint's MCP server (2.4+) is a third option for agent hosts.

---

## 6. Shorter entries: Cohere, Voyage AI, Jina AI, Mixedbread, Vectara, Pinecone Assistant, Ragie, Contextual AI, Glean

### Cohere
- **Offers**: embeddings, rerankers, Command LLMs with native RAG/citations, and "North" (agent platform; North Mini Code 1.0 2026-06-09, North Small Translate 1.0 2026-09-09 per [changelog filenames](https://github.com/cohere-ai/cohere-developer-experience/tree/main/fern/pages/changelog)).
- **Models (2026)**: **Embed 5** (2026-09-30): `embed-v5.0-pro` and `embed-v5.0-fast` (shared embedding space so index with Pro, query with Fast; 128K context; 100+ languages; 256–2048 dims; text+image; **$0.12 / 1M tokens Pro, $0.08 Fast**, image $0.40/1M) ([changelog](https://docs.cohere.com/v2/changelog); [AIwire 2026-10-01](https://www.hpcwire.com/aiwire/2026/10/01/cohere-releases-embed-5-with-pro-and-fast-tiers-for-enterprise-ai/)). Embed v4 (`embed-v4.0`, Matryoshka 256/512/1024/1536, 128k) is slated for retirement (date reads 2026-03-26 in changelog layout — ambiguous). **Rerank 4** (2025-12-11): `rerank-v4.0-pro`, `rerank-v4.0-fast`, 32k context, self-learning; OpenRouter lists $0.0025/search Pro, $0.002 Fast [third-party] ([Rerank 4 changelog](https://docs.cohere.com/changelog/rerank-v4.0)). **Command A+** (`command-a-plus-05-2026`, Apache-2.0, 218B/25B MoE, 128K in / 64K out, vision, native citations) ([model page](https://docs.cohere.com/docs/command-a-plus)); Command A Reasoning/Vision/Translate variants. **Parse v5** (2026-08-27 changelog) and **Transcribe** are newer component APIs.
- **Retrieve API?** No hosted index. Plug-in surface = `POST /v2/embed` (`input_type: search_document|search_query`, `embedding_types`), `POST /v2/rerank` (`query`, `documents[]`, `top_n`), and `POST /v2/chat` with `documents:[{id, data:{...}}]` → `message.citations[{start,end,text,sources[]}]` ([RAG citations](https://docs.cohere.com/docs/rag-citations)). Available on Bedrock, SageMaker, Azure Foundry, OCI. Model-provider adapter only.

### Voyage AI (MongoDB)
- **Offers**: embeddings and rerankers only (no index). **voyage-4** family (voyage-4-large $0.12/1M, voyage-4 $0.06, voyage-4-lite $0.02; 32K tokens; dims 256/512/1024/2048; shared space across the family; 200M free tokens; batch −33%), **voyage-context-4** (contextualized chunk embeddings: whole document in one request, ≤120K tokens / 16K chunks, $0.12/1M), **voyage-multimodal-3.5**, **rerank-3 / rerank-3-lite** ($0.05 / $0.02 per 1M tokens; rerank-2.5 32K, instruction-following) ([MongoDB-hosted Voyage docs](https://www.mongodb.com/docs/voyageai/models/); [billing](https://www.mongodb.com/docs/voyageai/management/billing/); aggregators [embeddingcost](https://embeddingcost.com/voyage)).
- **Plug-in**: `POST https://api.voyageai.com/v1/embeddings` (`input_type: query|document`, `output_dimension`), `/v1/contextualizedembeddings`, `/v1/rerank` (`query, documents, top_k`). Python `voyageai`. Model-provider adapter; `voyage-context-4` is attractive for our chunk contextualization step.

### Jina AI
- **Offers**: embeddings (**jina-embeddings-v5-text-small** 677M, Qwen3-0.6B base, 32K ctx, 1024-d Matryoshka→32; **v5-text-nano** 239M, 8K ctx, 768-d; released 2026-02-18; CC-BY-NC-4.0 open weights, commercial via Elastic/Jina API) ([Jina news](https://jina.ai/news/jina-embeddings-v5-text-distilling-4b-quality-into-sub-1b-multilingual-embeddings/); [Elastic blog 2026-02-23](https://www.elastic.co/search-labs/blog/jina-embeddings-v5-text)), **jina-reranker-v3.5** (drop-in for v3, 2026-07; CC-BY-NC) ([reranker page](https://jina.ai/reranker/)), v4 multimodal embeddings, Reader (`r.jina.ai` URL→markdown), Search (`s.jina.ai`), DeepSearch (agentic web research, 10K–300K tokens/query).
- **Pricing**: one shared token pool across APIs; 10M free tokens on new keys; ≈$0.02–0.05 / 1M tokens depending on model and source [conflicting; verify].
- **Plug-in**: OpenAI-style `POST https://api.jina.ai/v1/embeddings` (`task: retrieval.query|retrieval.passage`, `dimensions`, `late_chunking`), `POST /v1/rerank`. Model-provider adapter; Reader is useful for web/URL ingestion.

### Mixedbread
- **Offers**: hosted **Stores** (multimodal search over files/web: parsing, chunking, embedding, hybrid search, rerank, "agentic search" loop, regex grep, Q&A, query enhancement, facets, per-partition MCP) plus open-weight models (mxbai-embed-large-v1, Wholembed v3, mxbai-rerank-v2 Apache-2.0; v3-listwise proprietary) and the **Toast 1** search agent ($0.30/$0.72 per 1M in/out at launch) ([Search docs](https://www.mixedbread.com/docs/stores/search); [Agentic search](https://www.mixedbread.com/docs/stores/search/agentic-search); [pricing](https://www.mixedbread.com/pricing)).
- **API**: `POST https://api.mixedbread.com/v1/stores/search` `{ query, store_identifiers:[...], top_k:10, filters:{all:[{key,operator,value}]}, search_options:{ rerank:true, agentic:false }, file_ids, stream }` → chunk results (same shape in agentic mode). Pricing: Starter free ($5 credit, 10 stores, 100 RPM), Scale $20/mo (10k stores, 1,200 QPM), indexing $1.50 / 1M tokens, search ≈$4 / 1K basic, $7.50 / 1K with rerank, $20 / 1K agentic [third-party; conflicting with "$3.50/1K with rerank" on GitHub tracker].
- **Plug-in**: yes — direct retrieve API; good candidate for a "hosted multimodal store" backend.

### Vectara
- **Offers**: end-to-end "Enterprise Agent Platform": ingestion, Boomerang embeddings, hybrid retrieval, rerankers (Multilingual Reranker v1 "Slingshot", MMR, UDF), Mockingbird generation, HHEM hallucination scoring / Hallucination Corrector, agents with tools, SaaS/VPC/on-prem ([release notes](https://docs.vectara.com/docs/release-notes); [reranking](https://docs.vectara.com/docs/search-and-retrieval/reranking)).
- **API** ([Query a corpus](https://docs.vectara.com/docs/rest-api/query-corpus)): `POST https://api.vectara.io/v2/corpora/{corpus_key}/query` `{ query, search:{ limit:25, offset, metadata_filter:"doc.tenant='acme'", lexical_interpolation:0.025, context_configuration:{sentences_before,sentences_after}, reranker:{ type:"customer_reranker", reranker_name:"Rerank_Multilingual_v1" } | {type:"mmr", diversity_bias:0.3} | {type:"none"}, cutoff }, generation:{ generation_preset_name, max_used_search_results, citations:{style:"markdown"} } | null }` → `{ search_results:[{text, score, part_metadata, document_metadata, document_id}], summary, ... }`; multi-corpus `POST /v2/query`. Python SDK `vectara`.
- **Pricing 2026**: public free/growth tiers reportedly removed; SaaS from ~$100K/yr, VPC $250K, on-prem $500K, 30-day trial [third-party, conflicting] ([saaspartout](https://saaspartout.com/marketplace/vectara/); [futureagi](https://futureagi.com/blog/best-vectara-alternatives-2026/)). Enterprise-only now.
- **Plug-in**: yes (query with `generation: null` = pure retrieval), but commercial floor makes it an enterprise-only backend.

### Pinecone Assistant
- **Offers**: hosted RAG assistant: upload files (PDF/DOCX/MD/JSON/TXT, multimodal PDF), chat API, and a **context API** that returns raw snippets for your own LLM; MCP server per assistant ([pricing & limits](https://docs.pinecone.io/guides/assistant/pricing-and-limits); [context reference 2026-07](https://docs.pinecone.io/reference/api/2026-07/assistant/context_assistant); [MCP server](https://docs.pinecone.io/guides/assistant/mcp-server)).
- **API**: `POST https://{assistant-host}/assistant/chat/{name}/context` (header `X-Pinecone-Api-Version: 2026-07`) `{ query | messages, top_k:16 (≤64), snippet_size:2048 (512–8192), filter:{ genre:{ $ne:"x" } }, include_image_snippets }` → `{ id, snippets:[{ type:"text"|"image", content, score, reference:{ type:"pdf", file:{id,name,status,metadata}, pages:[78] } }], usage:{prompt_tokens,...} }`. MCP: `https://{host}/mcp/assistants/{name}` tool `assistant_context(assistant_name, query, top_k=15)`.
- **Pricing (2026 changelog)**: per-assistant hourly fee removed; context tokens **$5 / 1M**, chat $8/$15 per 1M in/out, ingestion $0.0005 / unit (~400 tokens; multimodal $0.001), storage; plan minimums Starter $0, Builder $20, Standard $50, Enterprise $500/mo ([2026 changelog](https://docs.pinecone.io/release-notes/2026)). Per-assistant file caps removed; limits now via ingestion/storage allowances, file size/pages, rate limits.
- **Plug-in**: yes — context API is exactly a retrieve endpoint (score + file/page reference).

### Ragie
- **Offers**: RAG-as-a-service with "Ragie Connect" managed connectors (Google Drive, Notion, Confluence, OneDrive, SharePoint, Salesforce, Gmail, S3, Backblaze, Freshdesk, …), multimodal ingestion (hi-res mode, audio/video), partitions (tenants), summary index, hybrid search, LLM rerank, recency bias, hosted streamable-HTTP MCP server per partition exposing a `retrieve` tool ([retrievals guide](https://docs.ragie.ai/docs/retrievals-guide); [connectors](https://www.ragie.ai/connectors); [MCP](https://docs.ragie.ai/docs/mcp-overview); [recency bias](https://docs.ragie.ai/docs/retrievals-recency-bias)).
- **API**: `POST https://api.ragie.ai/retrievals` `{ query, top_k:8, rerank:true, filter:{ department:{ $eq:"HR" } }, max_chunks_per_document:2, partition:"acme", recency_bias:true }` → `{ scored_chunks:[{ id, index, text, score, document_id, document_name, document_metadata, metadata, links }] }` (SDK camelCases). Python `ragie`, TS `ragie`.
- **Pricing**: Free dev (1k pages / 1k retrievals), Starter $100/mo (10k pages), Pro $500/mo (60k pages), overage $0.02 (fast) / $0.05 (hi-res) per page, storage $0.002/page-mo, first connector free then $250/connector/mo, enterprise custom ([pricing](https://www.ragie.ai/pricing)).
- **Plug-in**: yes — clean retrieve API with partitions for multi-tenancy.

### Contextual AI
- **Offers**: "RAG 2.0" platform with agents + datastores, plus component APIs: **Parse** (Basic text $3 / 1k pages, Standard multimodal $40 / 1k pages), **Rerank** (`ctxl-rerank-v2-instruct-multilingual` family; Rerank-v2 $0.05 / 1M tokens, Rerank-v2-mini $0.02; instruction-following), **Generate** (GLM, grounded LM, ~$3/$15 per 1M [third-party]), **LMUnit** eval, groundedness check ([pricing](https://contextual.ai/pricing); [Query API](https://docs.contextual.ai/api-reference/agents-query/query); [Rerank v2 blog](https://contextual.ai/blog/rerank-v2)).
- **API**: `POST https://api.contextual.ai/v1/agents/{agent_id}/query` `{ messages:[{role,content}], conversation_id, documents_filters, llm_model_id, override_configuration:{ enable_rerank, reranker, top_k_reranked_chunks, rerank_instructions, reranker_score_filter_threshold, ... }, retrievals_only:true }` → `{ message, retrieval_contents:[{ content_id, doc_id, doc_name, page, content_text, url, custom_metadata, score }], attributions }`. Also `/v1/rerank`, `/v1/parse`, `/v1/generate`, `/v1/datastores/{id}/documents`.
- **Plug-in**: yes via `retrievals_only` on the agent query (datastore-level retrieval with their rerank), or just use Parse/Rerank as components. $25 free credits.

### Glean
- **Offers**: enterprise search + assistant over 100+ SaaS connectors with permission-aware (ACL-trimmed) results; developer platform: Client API (search, chat, agents), Indexing API (push custom data), Platform API (version `2026-04-01`), remote MCP server (`mcp.glean.com` with tools search, chat, read_document, code_search, people_search; Gemini-specific MCP server 2026-10-13), Agent Identity GA 2026-10-01 ([API page](https://www.glean.com/platform/api); [Search API](https://developers.glean.com/api/client-api/search/search); [open-api repo](https://github.com/gleanwork/open-api); [release notes 2026-10-13](https://docs.glean.com/release-notes/releases/2026-10-13-october-release)).
- **API**: `POST https://{instance}-be.glean.com/rest/api/v1/search` (OAuth user token or Glean token) `{ query, pageSize:10, requestOptions:{ datasourcesFilter:["confluence","gdrive"], facetFilters:[...], facetBucketSize:10 } }` → `{ results:[{ title, url, document:{ id, datasource, docType, metadata }, snippets:[{ text, snippet }] }], facetResults, metadata }`; `/rest/api/v1/adminsearch` ignores permissions (privileged). SDKs: Python/TS/Go/Java `glean` (`client.client.search.query`).
- **Pricing**: per-seat enterprise (not public).
- **Plug-in**: yes, as a *federated, permission-aware* source: run the search on behalf of the user (OAuth) and treat `snippets` as chunks; note results are document-level with short snippets, not full passages — a `read_document`/document fetch step is needed for long context.

---

## 7. Anthropic guidance on retrieval

- **No hosted knowledge/vector retrieval tool as of 2026-10-16.** The Anthropic-provided server tools are web search (`web_search_20260318`, $10 / 1,000 searches, dynamic filtering via code execution), web fetch, code execution, advisor, tool search (BM25/regex over *tool definitions*, not documents), and the MCP connector; client tools include memory (`memory_20250818`, file-ops executed by your app, no similarity search), bash, text editor, computer/browser toolsets ([Tool reference, fetched 2026-10-16](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-reference); [web search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool)). Claude Managed Agents (beta `managed-agents-2026-04-01`) adds sandbox file ops, web search/fetch, MCP, memory stores and "dreams" — still no document index ([Managed Agents overview](https://platform.claude.com/docs/en/managed-agents/overview); [release notes](https://platform.claude.com/docs/en/release-notes/overview)). Retrieval is therefore *bring-your-own*; the recommended integration points are below.
- **Files API** (GA since 2025-08-19; beta header gone): `POST /v1/files` → `file_id`; reference in messages as `{"type":"document","source":{"type":"file","file_id":...},"citations":{"enabled":true}}` (PDF, text/plain) or `image`, or `container_upload` for code execution. Limits: 500 MB/file, 1 TB/org, ~500 RPM, optional `expires_in_seconds` (1h–90d); uploads free, content billed as input tokens; files are **workspace-scoped** (never accept user-supplied file_ids; one workspace per tenant, ≤100 workspaces/org) ([Files API, fetched](https://platform.claude.com/docs/en/build-with-claude/files)). It is a storage/deduplication convenience, not an index.
- **Citations** (GA on all platforms): enable per `document` block; citation types `char_location` (text docs), `page_location` (PDF), `content_block_location` (custom content docs), `web_search_result_location`, `search_result_location`; cited text does not count toward output tokens ([Citations](https://platform.claude.com/docs/en/build-with-claude/citations)).
- **`search_result` content blocks** (GA 2025-08-08, no beta header): the canonical way to feed *our* retrieval results to Claude, either as tool results or top-level user content: `{"type":"search_result","source":"<url or id>","title":"...","content":[{"type":"text","text":"..."}],"citations":{"enabled":true}}` → Claude cites with `search_result_location {source,title,cited_text,search_result_index,start_block_index,end_block_index}` ([Search results](https://platform.claude.com/docs/en/build-with-claude/search-results)). Note: citations on documents + `output_config.format` (structured output) returns 400.
- **Contextual Retrieval** (Anthropic engineering, 2024-09): prepend a 50–100-token LLM-generated context to each chunk (prompt: whole doc cached + chunk → "succinct context… answer only with the context"), index both embeddings and BM25 over contextualized chunks, fuse with RRF, retrieve ~150 then rerank to top-20. Reported top-20 retrieval failure: 5.7% → 3.7% (contextual embeddings) → 2.9% (+contextual BM25) → 1.9% (+reranking). One-time cost ≈ **$1.02 / 1M document tokens** with prompt caching. Recommendations: chunks of a few hundred tokens, pass 20 chunks, domain-tailored contextualizer prompt, and **skip RAG entirely below ~200K tokens (~500 pages) — just cache the corpus in the prompt** ([Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval); cookbook at `anthropics/anthropic-cookbook/skills/contextual-embeddings`).
- Other relevant primitives: prompt caching (1h TTL GA), PDF support (page-level citations, split dense PDFs), MCP connector (`mcp_toolset`, beta `mcp-client-2025-11-20`) for calling any of the backends above that expose MCP (Foundry IQ KB, Bedrock via AgentCore Gateway, Pinecone Assistant, Ragie, Mixedbread, Glean, NVIDIA blueprint).

---

## Comparison table

Legend: ✔ built-in, ◐ partial / preview / add-on, ✘ absent, BYO = bring your own.

| Platform | Hybrid search | Reranking | Query planning / decomposition | Multimodal / doc parsing | GraphRAG | Permission trimming / ACL | MCP endpoint | Citations | Pricing unit |
|---|---|---|---|---|---|---|---|---|---|
| **Foundry IQ / Azure AI Search KB** | ✔ (vector+BM25 per sub-query) | ✔ semantic ranker (L2/L3) | ✔ LLM planning, parallel sub-queries, iterative at `medium` (preview) | ◐ indexer skillset (Blob/OneLake/SharePoint; images via AI Vision skills) | ✘ | ✔ SharePoint remote (Copilot Retrieval API, user token), ADLS/SharePoint ACL ingestion (preview), Purview labels | ✔ per-KB `/mcp` (`knowledge_base_retrieve`, preview) | ✔ `references[]` + synthesized answer citations | Retrieval tokens (Azure AI Search, 50M free/mo) + Azure OpenAI tokens; remote sources extra |
| **Bedrock Knowledge Bases** | ✔ (OpenSearch; managed KB always hybrid) | ✔ Amazon Rerank / Cohere 3.5; managed reranker included | ◐ `QUERY_DECOMPOSITION` in R&G; ✔ `AgenticRetrieveStream` (managed only) | ✔ BDA / FM parser; Nova multimodal embeddings; audio/video (BDA) | ✔ Neptune Analytics (custom KB, S3 only) | ✔ managed KB doc-level ACL (`userContext`); custom KB via metadata filters | ◐ via AgentCore Gateway KB target | ✔ R&G `citations[]`; Retrieve returns `location`+`metadata` | $1 / 1k Retrieve; $4 / 1k agentic; $5 / GB-mo (managed); vector store + model tokens (custom) |
| **Vertex AI RAG Engine** | ◐ (Weaviate backend only; vector otherwise) | ✔ `rank_service` or `llm_ranker` | ✘ (Gemini does it when used as a tool) | ◐ layout parser (Document AI), LLM parser; text queries only | ✘ | ✘ (metadata filters only) | ◐ Google MCP tools reference lists `retrieve_contexts` | ◐ via Gemini `grounding_metadata` / `corroborateContent` | Spanner instance hours + embedding/LLM tokens; no per-call fee |
| **Vertex AI Search / Agent Search** | ✔ | ✔ built-in | ✔ query rephrasing (`answer`), classification | ✔ (PDF/HTML/structured; connectors) | ✘ | ✔ for connector data stores (IdP-synced ACLs) | ◐ (Agent Platform MCP tools) | ✔ `summaryWithMetadata` / `answer.citations` | $1.50 / 1k (Std) – $4 / 1k (Ent) queries + $5 / GiB-mo index |
| **OpenAI file_search / Vector Stores** | ✔ RRF with tunable weights | ✔ `ranker: auto/default-2024-11-15` | ◐ query rewrite; multi-query inside model loop | ◐ many text formats; no images/audio in stores | ✘ | ✘ (attributes filters only) | ✘ | ✔ `file_citation` annotations | $2.50 / 1k tool calls + $0.10 / GB-day (1 GB free) |
| **NVIDIA RAG Blueprint + NIMs** | ✔ dense+sparse (Elasticsearch/Milvus), weighted | ✔ llama-nemotron-rerank (text/VL) | ✔ decomposition, rewriting, filter generation, agentic plan-and-execute (2.6) | ✔ NV-Ingest: text, tables, charts, infographics, OCR, audio; VLM embeddings | ✘ | ✘ | ✔ MCP server (2.4+) | ✔ image/table/chart citations | Self-hosted GPUs / NVIDIA AI Enterprise; hosted NIM endpoints free-tier (no list $) |
| **Cohere** | BYO | ✔ Rerank 4 pro/fast | ✘ | ◐ Embed 5 text+image; Parse v5 | ✘ | ✘ | ✘ | ✔ native citations in Chat `documents` | $/1M tokens (embed), $/search (rerank), $/1M tokens (Command) |
| **Voyage AI** | BYO | ✔ rerank-3 / 2.5 | ✘ | ◐ multimodal-3.5; context-4 chunk contextualization | ✘ | ✘ | ✘ | ✘ | $/1M tokens (200M free) |
| **Jina AI** | BYO | ✔ reranker v3.5 | ◐ DeepSearch (web) | ◐ v4 multimodal embeddings; Reader | ✘ | ✘ | ✘ | ✘ | shared $/1M token pool (10M free) |
| **Mixedbread Stores** | ✔ | ✔ (+ listwise v3) | ✔ agentic search loop; query enhancement | ✔ multimodal files + web stores | ✘ | ✘ (store/partition scoping) | ✔ per store | ◐ chunk refs | $/1k queries by mode + $1.50 / 1M tokens indexing |
| **Vectara** | ✔ (lexical interpolation) | ✔ multilingual, MMR, UDF | ◐ agents | ◐ multimodal ingestion | ✘ | ◐ metadata filters; enterprise RBAC | ◐ | ✔ generation citations | Enterprise annual contracts (≈$100K+ SaaS) |
| **Pinecone Assistant** | ✔ | ✔ | ✘ (chat does multi-query internally) | ✔ multimodal PDF | ✘ | ✘ (metadata filters) | ✔ per assistant | ✔ file + page refs | $5 / 1M context tokens, ingestion units, storage; plan minimums |
| **Ragie** | ✔ | ✔ LLM rerank | ✘ | ✔ hi-res docs, audio/video | ✘ | ◐ partitions + metadata filters | ✔ per partition | ✔ chunk→document links | $/page processed + $/connector/mo + plan |
| **Contextual AI** | ✔ | ✔ instruction rerank v2 | ◐ query optimization/multi-turn | ✔ Parse (multimodal) | ✘ | ◐ datastore filters | ✘ | ✔ attributions / groundedness | $/page (parse), $/1M tokens (rerank, generate) |
| **Glean** | ✔ | ✔ | ◐ (chat/agents) | ◐ connector-dependent | ✘ (knowledge graph internal) | ✔ full enterprise ACL trimming | ✔ `mcp.glean.com` | ◐ document links/snippets | per seat (enterprise) |
| **Anthropic (Claude API)** | BYO | BYO | BYO (model) | ✔ PDF/images in context | ✘ | ✘ | ✔ MCP *client* connector | ✔ `search_result_location`, `page_location`, etc. | tokens; web search $10 / 1k |

### Design takeaways for a pluggable retrieval engine
1. Every hosted backend converges on a **`retrieve(query, filters, top_k) → [{text, score, source_uri/doc_id, metadata, page/span}]`** primitive, plus an optional **trace** (Azure `activity[]`, Bedrock agentic events, Mixedbread stream, OpenAI `queries[]`). Our backend interface should expose both.
2. Two backends do **server-side query planning** (Azure `low/medium`, Bedrock `AgenticRetrieveStream`, Mixedbread `agentic`, NVIDIA `agentic`); the rest expect the orchestrating LLM to decompose. Model this as a capability flag so our planner is skipped when the backend plans.
3. **MCP is now the common agent-facing transport** (Azure KB, Bedrock via AgentCore, Pinecone, Ragie, Mixedbread, Glean, NVIDIA). A generic `McpRetriever` adapter (tool name + arg mapping) covers several vendors at once.
4. **Permission trimming** exists only where identity flows through (Azure remote SharePoint / ACL ingestion, Bedrock `userContext`, Agent Search connector stores, Glean). Our interface needs a `principal`/`user_token` field, and metadata-filter-based emulation elsewhere.
5. Pricing units differ (tokens vs calls vs pages vs GB-days vs Spanner hours); the engine should emit per-call cost estimates per backend.
6. Claude-side: feed results as `search_result` blocks with `citations.enabled` to get precise, token-free citations; apply Contextual Retrieval at ingest for backends where we control chunking (OpenAI static chunking, self-hosted NVIDIA, Bedrock custom chunking Lambda), and bypass RAG under ~200K tokens with prompt caching.
