"""
Structured JSON logging configuration using structlog.

Provides request tracing, timing metrics, and consistent log formatting
across the entire application.
"""

import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime
from functools import wraps
from typing import Any, Callable

import structlog

# Context variable for request tracing
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
user_id_ctx: ContextVar[str] = ContextVar("user_id", default="")


def add_request_context(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Add request context (request_id, user_id) to log events."""
    request_id = request_id_ctx.get()
    user_id = user_id_ctx.get()
    
    if request_id:
        event_dict["request_id"] = request_id
    if user_id:
        event_dict["user_id"] = user_id
    
    return event_dict


def add_timestamp(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Add ISO timestamp to log events."""
    event_dict["timestamp"] = datetime.utcnow().isoformat() + "Z"
    return event_dict


def add_service_info(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Add service information to log events."""
    event_dict["service"] = "rag-backend"
    return event_dict


def setup_logging(
    log_level: str = "INFO",
    json_logs: bool = True,
    log_to_file: bool = False,
    log_file_path: str = "logs/app.log",
) -> None:
    """
    Configure structured logging for the application.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_logs: If True, output JSON formatted logs (recommended for production)
        log_to_file: If True, also log to a file
        log_file_path: Path to the log file
    """
    # Set log level
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Configure shared processors
    shared_processors: list[structlog.types.Processor] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        add_timestamp,
        add_service_info,
        add_request_context,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]
    
    # Configure final processor based on output format
    if json_logs:
        final_processor = structlog.processors.JSONRenderer()
    else:
        final_processor = structlog.dev.ConsoleRenderer(colors=True)
    
    # Configure structlog
    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configure standard library logging
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=final_processor,
        foreign_pre_chain=shared_processors,
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(numeric_level)
    
    handlers = [console_handler]
    
    # File handler (optional)
    if log_to_file:
        import os
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(numeric_level)
        handlers.append(file_handler)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    root_logger.handlers = handlers
    
    # Suppress noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        Configured structlog bound logger
    """
    return structlog.get_logger(name)


def generate_request_id() -> str:
    """Generate a unique request ID for tracing."""
    return str(uuid.uuid4())


def set_request_context(request_id: str, user_id: str = "") -> None:
    """Set request context variables for logging."""
    request_id_ctx.set(request_id)
    user_id_ctx.set(user_id)


def clear_request_context() -> None:
    """Clear request context variables."""
    request_id_ctx.set("")
    user_id_ctx.set("")


def log_timing(operation: str) -> Callable:
    """
    Decorator to log execution time of functions.
    
    Args:
        operation: Name of the operation being timed
        
    Example:
        @log_timing("embedding_generation")
        async def generate_embeddings(text: str):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger = get_logger(func.__module__)
            start_time = datetime.utcnow()
            
            try:
                result = await func(*args, **kwargs)
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                logger.info(
                    f"{operation} completed",
                    operation=operation,
                    duration_ms=round(duration_ms, 2),
                    status="success",
                )
                return result
            except Exception as e:
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                logger.error(
                    f"{operation} failed",
                    operation=operation,
                    duration_ms=round(duration_ms, 2),
                    status="error",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger = get_logger(func.__module__)
            start_time = datetime.utcnow()
            
            try:
                result = func(*args, **kwargs)
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                logger.info(
                    f"{operation} completed",
                    operation=operation,
                    duration_ms=round(duration_ms, 2),
                    status="success",
                )
                return result
            except Exception as e:
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                logger.error(
                    f"{operation} failed",
                    operation=operation,
                    duration_ms=round(duration_ms, 2),
                    status="error",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                raise
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


class LoggingContext:
    """
    Context manager for adding temporary context to logs.
    
    Example:
        with LoggingContext(operation="chat", session_id="123"):
            logger.info("Processing request")
    """
    
    def __init__(self, **kwargs):
        self.context = kwargs
        self.token = None
    
    def __enter__(self):
        # Store context for structured logging
        structlog.contextvars.bind_contextvars(**self.context)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        structlog.contextvars.unbind_contextvars(*self.context.keys())
        return False
