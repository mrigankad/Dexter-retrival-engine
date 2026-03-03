# ============================================
# Dexter Retrieval Agent - Makefile
# ============================================

.PHONY: help build up down logs test clean dev

# Default target
help:
	@echo "Dexter Retrieval Agent - Available Commands"
	@echo "============================================"
	@echo ""
	@echo "Docker Commands:"
	@echo "  make build       - Build all Docker images"
	@echo "  make up          - Start all services"
	@echo "  make down        - Stop all services"
	@echo "  make restart     - Restart all services"
	@echo "  make logs        - View logs (all services)"
	@echo "  make logs-api    - View API logs"
	@echo "  make ps          - Show running containers"
	@echo ""
	@echo "Development:"
	@echo "  make dev         - Run API locally for development"
	@echo "  make test        - Run tests"
	@echo "  make lint        - Run linting"
	@echo "  make clean       - Clean up containers and volumes"
	@echo ""
	@echo "Database:"
	@echo "  make db-migrate  - Run database migrations"
	@echo "  make db-reset    - Reset database"
	@echo ""

# ============================================
# Docker Commands
# ============================================

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

# ============================================
# Development Commands
# ============================================

dev:
	cd backend && python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

dev-worker:
	cd backend && python -m ingestion.ingest_worker

install:
	cd backend && pip install -r requirements.txt

test:
	cd backend && pytest tests/ -v --cov=. --cov-report=term-missing

test-unit:
	cd backend && pytest tests/unit/ -v

test-integration:
	cd backend && pytest tests/integration/ -v

lint:
	cd backend && python -m flake8 . --max-line-length=120

format:
	cd backend && python -m black .

# ============================================
# Database Commands
# ============================================

db-migrate:
	cd backend && alembic upgrade head

db-reset:
	docker compose down -v
	docker compose up -d postgres
	@echo "Waiting for PostgreSQL to start..."
	@sleep 5
	docker compose up -d

# ============================================
# Cleanup Commands
# ============================================

clean:
	docker compose down -v --remove-orphans
	docker system prune -f

clean-images:
	docker compose down
	docker rmi $$(docker images -q 'rag-*') 2>/dev/null || true

# ============================================
# Quick Start
# ============================================

init: build up
	@echo "============================================"
	@echo "RAG Backend is starting..."
	@echo "API will be available at http://localhost:8000"
	@echo "API Docs at http://localhost:8000/docs"
	@echo "============================================"
	@echo "Run 'make logs' to view logs"

# ============================================
# Production
# ============================================

prod-build:
	docker compose -f docker-compose.yml build --no-cache

prod-up:
	docker compose -f docker-compose.yml up -d

prod-down:
	docker compose -f docker-compose.yml down
