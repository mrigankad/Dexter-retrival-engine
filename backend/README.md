# Backend

FastAPI service for the Bodham Retrieval Engine. See [`../docs/ARCHITECTURE_V3.md`](../docs/ARCHITECTURE_V3.md) for the design.

```
main.py                 application entry point
src/contracts/          shared Pydantic contracts
src/core/               config, logging, security, dependencies
src/infrastructure/     database, vector_store (Qdrant hybrid), cache
src/services/llm/       NVIDIA NIM chat / embedding / reranker clients (+ legacy services)
src/ingestion/          parsers, chunker, pipeline, worker
src/retrieval/          hybrid retriever, fusion, context builder
src/knowledge/          knowledge adapters (local, foundry_iq, mock) + registry
src/orchestrator/       router, planner, executor, synthesizer, engine
src/evaluation/         eval harness
src/api/v1/             routes
src/agents/             legacy multi-agent package (/api/agents)
tests/                  pytest suite (unit, integration, agents)
scripts/                run_eval.py, reingest.py, query_test.py
reports/                legacy report builders (optional deps)
```

## Run

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt            # + requirements-optional.txt for Docling, local reranker, MinIO, Neo4j, RAGAS
USE_SQLITE=true QDRANT_MODE=path REDIS_ENABLED=false INGESTION_MODE=inline uvicorn main:app --reload
python -m src.ingestion.worker             # queue worker (needs Redis, INGESTION_MODE=queue)
python -m pytest -q                        # tests
python scripts/run_eval.py --dataset ../evals/datasets/sample.json
```
