<div align="center">

# 🚀 Context RAG (Dexter Retrieval Agent)

**An Enterprise-Grade, Multi-Agent Retrieval Augmented Generation System**
<br>
Powered by **NVIDIA NIM APIs**, **FastAPI**, and **Qdrant**

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg?logo=docker&logoColor=white)](https://docker.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-20232A?logo=react&logoColor=61DAFB)](https://reactjs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

</div>

---

## 📖 Overview

Context RAG is a sophisticated, production-ready RAG platform designed to answer complex domain-specific analytical queries from large, dense documents (400+ pages). It has evolved from standard RAG to a **Planner-Driven Multi-Hop Retrieval** system featuring **Advanced Multimodal Ingestion**. 

### ✨ Core Features

- 🧠 **Agentic Reasoning Orchestration**: Multi-hop query execution and query planning via Llama 3.1 70B Architect agents.
- 📄 **Multimodal Document Processing**: Extracts and understands PDFs, DOCX, Tables, and Charts (powered by Docling & LLaVA).
- 🔍 **Hybrid Vector Search**: Qdrant-powered dense (NV-EmbedQA) + sparse (Splade/BM25) search with Reciprocal Rank Fusion & NVIDIA Mistral Reranking.
- 💬 **Streaming Telemetry**: Real-time Server-Sent Events (SSE) with Langfuse observability.
- 🔐 **Enterprise Security**: JWT Authentication, Rate Limiting, and Role-Based Access controls ready.
- 🐳 **Seamless Deployment**: Fully Dockerized, one-click `docker compose up` setup.

---

## 🏗️ Architecture Design

The system is designed with a multi-layered reasoning engine and high-throughput ingestion pipeline.

```mermaid
graph TD
    %% Define Styles
    classDef user fill:#6c5ce7,stroke:#fff,stroke-width:2px,color:#fff,font-weight:bold;
    classDef core fill:#0984e3,stroke:#fff,stroke-width:2px,color:#fff,font-weight:bold;
    classDef component fill:#00b894,stroke:#fff,stroke-width:2px,color:#fff;
    classDef storage fill:#d63031,stroke:#fff,stroke-width:2px,color:#fff,font-weight:bold;

    UserQuery((User Query)):::user -->|HTTP| API_Gateway[FastAPI Gateway]:::core
    API_Gateway --> QueryClassifier[Query Classifier Agent]:::component
    
    subgraph "Reasoning Engine"
        QueryClassifier -- "Simple" --> StandardRAG[Standard RAG Execution]:::component
        QueryClassifier -- "Complex" --> PlannerAgent[Planner Agent (Llama 70B)]:::component
        PlannerAgent -->|Decomposed Plan| Orchestrator[Multi-Hop Orchestrator]:::component
        
        Orchestrator --> HybridRetrieval1[Hybrid Search Path A]:::component
        Orchestrator --> HybridRetrieval2[Hybrid Search Path B]:::component
        
        HybridRetrieval1 --> RRF_Fusion[Reciprocal Rank Fusion]:::component
        HybridRetrieval2 --> RRF_Fusion
        
        RRF_Fusion -->|Top 50 Chunks| Reranker[NVIDIA Reranker]:::component
        Reranker -->|Top 5 Chunks| ContextCompressor[Context Compressor]:::component
        ContextCompressor --> SynthesisEngine[Synthesis Engine]:::core
    end
    
    subgraph "Knowledge Base"
        PDF_Upload[(Raw Documents)]:::storage --> DoclingParser[Docling Parser]:::component
        DoclingParser --> ContentRouter[Content Router]:::component
        
        ContentRouter -- Tables --> TableCanonicalizer[Table Canonicalizer]:::component
        ContentRouter -- Charts --> ChartAnalyzer[VLM Chart Analysis]:::component
        ContentRouter -- Text --> SemanticChunker[Hierarchical Chunker]:::component
        
        TableCanonicalizer & ChartAnalyzer & SemanticChunker --> Qdrant[(Qdrant Vector DB)]:::storage
    end
    
    Qdrant -.-> HybridRetrieval1
    Qdrant -.-> HybridRetrieval2
    
    SynthesisEngine --> FinalResponse((Final Response)):::user
```

---

## 🚀 Quick Start (Dockerized)

### Prerequisites
- Docker & Docker Compose
- **NVIDIA API Key** (Create an account at [build.nvidia.com](https://build.nvidia.com))

### Installation

**1. Clone the Repository & Configure Environment**
```bash
git clone https://github.com/mrigankad/context-rag.git
cd context-rag

# Copy environment template
cp .env.example .env

# Edit .env and append your credentials
# NVIDIA_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxxxxxxxx
```

**2. Start the Stack**
```bash
make init
# Or manually: docker compose up -d
```

**3. Verify Services**
```bash
# Check service health
curl http://localhost:8000/health

# View API documentation (Swagger UI)
# Open http://localhost:8000/docs in your browser
```

---

## 📈 Roadmap & Progress tracker

The project is structured across 4 distinct phases, moving from stability, to multi-agent capabilities, and finally to highly scaled multi-tenant clusters.

| Phase | Category | Goal / Feature | Status | Priority |
|:---:|---|---|:---:|:---:|
| **Phase 1** | **Performance** | Vector Query & Database Pool Optimization (<3s Latency)| 🔄 In Progress | 🔴 High |
| **Phase 1** | **Telemetry** | Prometheus & Grafana System Dashboards | ⏳ Planned | 🟡 Medium |
| **Phase 1** | **Quality** | Unit, Integration, & Latency Benchmark Tests (75% Coverage)| 🔄 In Progress | 🔴 High |
| **Phase 2** | **Reasoning** | Deep Agentic Reasoning (Thought-Action loop, Follow-ups) | ⏳ Planned | 🔴 High |
| **Phase 2** | **Ingestion** | Advanced Table Preservation & Visual Graph Mapping | ⏳ Planned | 🟡 Medium |
| **Phase 2** | **Verification** | Entailment checking & Hallucination detection | ⏳ Planned | 🔴 High |
| **Phase 3** | **Scaling** | K8s Horizontal Pod Autoscaling (HPA) & Qdrant Sharding | ⏳ Planned | 🔴 High |
| **Phase 3** | **Data** | Incremental Indexing (Diff detection without full re-processing) | ⏳ Planned | 🟡 Medium |
| **Phase 4** | **Enterprise** | Multi-Tenancy (Row-level Security, DB logical separation) | ⏳ Planned | 🔴 High |
| **Phase 4** | **Finetuning** | Domain-Specific Custom Re-rankers & Embeddings | ⏳ Planned | 🟢 Low |

---

## ⚙️ Core Configuration 

Key environment variables in your `.env` file:

| Variable | Default Value | Description |
|----------|---------------|-------------|
| `NVIDIA_API_KEY` | *(Required)* | Grants access to NIM inference scaling. |
| `NVIDIA_LLM_MODEL` | `meta/llama-3.1-70b-instruct` | Primary LLM for Synthesis & Planning. |
| `NVIDIA_EMBED_MODEL`| `nvidia/nv-embedqa-e5-v5` | Dense Embedding Model (1024 dims). |
| `CHUNK_SIZE` | `512` | Token length per semantic chunk. |
| `TOP_K_RETRIEVAL` | `5` | Final chunk count returned after reranking. |

---

## 📁 Repository Structure

```tree
Context RAG/
├── backend/               # FastAPI Backend Application
│   ├── api/               # API Routes & Controllers
│   ├── core/              # Security, Logging, and App Config
│   ├── ingestion/         # Docling Parsers & Multi-Modal Extractors
│   ├── workflow/          # Multi-Hop Exec, Langchain Orchestration
│   └── main.py            # App Entrypoint
├── frontend/              # React UI Dashboard
├── docker/                # Isolated Dockerfiles for Build Targets
├── docs/                  # Architecture, Feature Designs, Specifications
├── scripts/               # CI/CD and DB migration utilities
├── docker-compose.yml     # Local orchestration map
├── Makefile               # Task runner
└── README.md              # You are here
```

---

## 🔐 Security & Safety
- **Traffic Safety**: NeMo Guardrails enabled for Input/Output sanitization.
- **Authentication**: Stateless, Redis-backed JWTs with route-level Access Control.

## 🤝 Contributing
Contributions are welcome! Please ensure you check the `docs/` directory for Architectural guidelines before opening PRs. 

## 📝 License
This project is licensed under the **MIT License**.

<div align="center">
<i>Built with ❤️ using NVIDIA NIMs</i>
</div>
