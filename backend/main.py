"""
NVIDIA NIM RAG Backend - Main Application Entry Point
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import settings
from core.logger import setup_logging, get_logger, generate_request_id, set_request_context, clear_request_context
from core.dependency_injection import close_redis
from db.session_manager import init_db

# Initialize logging
setup_logging(log_level=settings.log_level, json_logs=settings.is_production)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    logger.info("Starting application", app_name=settings.app_name, environment=settings.app_env)
    await init_db()
    yield
    logger.info("Shutting down application")
    await close_redis()


app = FastAPI(
    title="NVIDIA NIM RAG Backend",
    description="Production-ready RAG backend powered by NVIDIA NIM APIs",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else ["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    """Request logging and tracing middleware."""
    request_id = request.headers.get("X-Request-ID") or generate_request_id()
    set_request_context(request_id)
    request.state.request_id = request_id
    
    logger.info("Request started", method=request.method, path=request.url.path)
    
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info("Request completed", status_code=response.status_code)
        return response
    except Exception as e:
        logger.exception("Request failed", error=str(e))
        raise
    finally:
        clear_request_context()


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    from fastapi import HTTPException
    
    request_id = getattr(request.state, "request_id", "unknown")
    
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail, "request_id": request_id},
        )
    
    logger.exception("Unhandled exception", error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal server error", "request_id": request_id},
    )


# Import and register routers
from api.health_routes import router as health_router
from api.auth_routes import router as auth_router
from api.chat_routes import router as chat_router
from api.ingestion_routes import router as ingestion_router
from api.report_routes import router as report_router
from api.evaluation_routes import router as evaluation_router

app.include_router(health_router, prefix="", tags=["Health"])
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(chat_router, prefix="/chat", tags=["Chat"])
app.include_router(ingestion_router, prefix="", tags=["Ingestion"])
app.include_router(report_router, prefix="", tags=["Reports"])
app.include_router(evaluation_router, prefix="/evaluations", tags=["Evaluation"])


@app.get("/", include_in_schema=False)
async def root():
    return {"name": settings.app_name, "version": "1.0.0", "status": "running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.api_host, port=settings.api_port, reload=settings.debug)
