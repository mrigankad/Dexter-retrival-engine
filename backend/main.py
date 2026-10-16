"""
Bodham Retrieval Engine - FastAPI application.

Routes are mounted twice: at their legacy paths (used by the bundled React UI)
and under ``/v1`` (the versioned contract).
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.core.config import settings
from src.core.logger import clear_request_context, generate_request_id, get_logger, set_request_context, setup_logging

setup_logging(log_level=settings.log_level, json_logs=settings.is_production)
logger = get_logger(__name__)

APP_VERSION = "2.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    from src.core.dependency_injection import close_redis
    from src.infrastructure.database import close_db, init_db
    from src.services.llm.embedding_service import EmbeddingService
    from src.services.llm.nvidia_llm_service import NvidiaLLMService
    from src.services.llm.reranker_service import RerankerService

    logger.info("Starting application", app_name=settings.app_name, environment=settings.app_env,
                knowledge_backend=settings.knowledge_backend, qdrant_mode=settings.qdrant_mode,
                database=settings.effective_database_url.split(":")[0], llm_configured=settings.has_nvidia_key)
    os.makedirs(settings.upload_dir, exist_ok=True)
    await init_db()
    if settings.knowledge_backend == "local":
        try:
            from src.infrastructure.vector_store import get_qdrant_store
            await get_qdrant_store().ensure_collection()
        except Exception as exc:
            logger.warning("Qdrant not reachable at startup; will retry on first use", error=str(exc))
    if not settings.has_nvidia_key:
        logger.warning("NVIDIA_API_KEY is not set: embedding, reranking and answer generation will fail until configured")
    if settings.tracing_enabled:
        try:
            from src.core.telemetry import setup_telemetry
            setup_telemetry(app)
        except Exception as exc:
            logger.warning("Telemetry setup failed", error=str(exc))
    if settings.mcp_server_enabled:
        from src.mcp_server import mcp_lifespan
        async with mcp_lifespan():
            logger.info("MCP server mounted", path="/mcp", auth_required=settings.mcp_require_auth)
            yield
    else:
        yield
    logger.info("Shutting down application")
    from src.ingestion.worker import wait_for_inline_jobs
    await wait_for_inline_jobs()
    await NvidiaLLMService.aclose()
    await EmbeddingService.aclose()
    await RerankerService.aclose()
    await close_redis()
    await close_db()


app = FastAPI(
    title="Bodham Retrieval Engine",
    description="Pluggable enterprise retrieval engine: hybrid search, reranking, planned multi-hop retrieval, "
                "cited synthesis, and swappable knowledge backends (local Qdrant, Microsoft Foundry IQ).",
    version=APP_VERSION,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug and settings.cors_origins == "*" else settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Session-ID"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or generate_request_id()
    set_request_context(request_id)
    request.state.request_id = request_id
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        clear_request_context()


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail, "request_id": request_id},
                            headers=getattr(exc, "headers", None))
    logger.exception("Unhandled exception", error=str(exc))
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        content={"error": "Internal server error", "request_id": request_id})


from src.api.v1.agents_routes import router as agents_router  # noqa: E402
from src.api.v1.auth_routes import router as auth_router  # noqa: E402
from src.api.v1.chat_routes import router as chat_router  # noqa: E402
from src.api.v1.evaluation_routes import router as evaluation_router  # noqa: E402
from src.api.v1.health_routes import router as health_router  # noqa: E402
from src.api.v1.ingestion_routes import router as ingestion_router  # noqa: E402
from src.api.v1.knowledge_routes import router as knowledge_router  # noqa: E402
from src.api.v1.trace_routes import router as trace_router  # noqa: E402

for prefix in ("", "/v1"):
    tag_suffix = " (v1)" if prefix else ""
    app.include_router(health_router, prefix=prefix, tags=["Health" + tag_suffix], include_in_schema=not prefix)
    app.include_router(auth_router, prefix=f"{prefix}/auth", tags=["Authentication" + tag_suffix], include_in_schema=not prefix)
    app.include_router(chat_router, prefix=f"{prefix}/chat", tags=["Chat" + tag_suffix], include_in_schema=not prefix)
    app.include_router(ingestion_router, prefix=prefix, tags=["Documents" + tag_suffix], include_in_schema=not prefix)
    app.include_router(knowledge_router, prefix=f"{prefix}/knowledge", tags=["Knowledge" + tag_suffix], include_in_schema=not prefix)
    app.include_router(trace_router, prefix=f"{prefix}/traces", tags=["Traces" + tag_suffix], include_in_schema=not prefix)
    app.include_router(evaluation_router, prefix=f"{prefix}/evaluations", tags=["Evaluation" + tag_suffix], include_in_schema=not prefix)
app.include_router(agents_router, tags=["Multi-Agent (experimental)"])

if settings.mcp_server_enabled:
    from src.mcp_server import mcp_asgi_app
    app.mount("/mcp", mcp_asgi_app(), name="mcp")


@app.get("/", include_in_schema=False)
async def root():
    return {"name": settings.app_name, "version": APP_VERSION, "status": "running",
            "knowledge_backend": settings.knowledge_backend, "docs": "/docs" if settings.debug else None}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.api_host, port=settings.api_port, reload=settings.debug)
