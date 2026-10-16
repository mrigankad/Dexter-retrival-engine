# ============================================
# Dexter Retrieval Engine - Makefile
# ============================================

.PHONY: help build up down restart logs logs-api logs-worker ps dev dev-worker install install-optional test test-unit test-integration lint format eval clean init

help:
	@echo "Docker:      make build | up | down | restart | logs | logs-api | logs-worker | ps | init"
	@echo "Local dev:   make install | install-optional | dev | dev-worker | dev-local (no Docker services)"
	@echo "Quality:     make test | test-unit | test-integration | lint | format"
	@echo "Evaluation:  make eval DATASET=evals/datasets/sample.json"
	@echo "Cleanup:     make clean"

# ---------- Docker ----------
build:
	docker compose build
up:
	docker compose up -d
down:
	docker compose down
restart: down up
logs:
	docker compose logs -f
logs-api:
	docker compose logs -f api
logs-worker:
	docker compose logs -f ingestion-worker
ps:
	docker compose ps
init: build up
	@echo "API: http://localhost:8000  (docs at /docs)   UI: http://localhost:3000"

# ---------- Local development ----------
install:
	cd backend && python -m pip install -r requirements.txt
install-optional:
	cd backend && python -m pip install -r requirements-optional.txt
dev:
	cd backend && python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
dev-worker:
	cd backend && python -m src.ingestion.worker
# Zero-dependency run: SQLite + in-process Qdrant + inline ingestion (needs NVIDIA_API_KEY only)
dev-local:
	cd backend && USE_SQLITE=true QDRANT_MODE=path REDIS_ENABLED=false INGESTION_MODE=inline \
		python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

# ---------- Quality ----------
test:
	cd backend && python -m pytest -q
test-unit:
	cd backend && python -m pytest -q tests/unit tests/agents
test-integration:
	cd backend && python -m pytest -q tests/integration
lint:
	cd backend && python -m ruff check src tests || python -m flake8 src tests --max-line-length=130
format:
	cd backend && python -m ruff format src tests || python -m black src tests

# ---------- Evaluation ----------
DATASET ?= evals/datasets/sample.json
eval:
	cd backend && python scripts/run_eval.py --dataset ../$(DATASET) --top-k 8

# ---------- Cleanup ----------
clean:
	docker compose down -v --remove-orphans
