"""
OpenTelemetry Observability Module.

Provides distributed tracing, metrics, and logging integration:
- OpenTelemetry tracing with OTLP export
- Prometheus metrics
- Structured logging correlation
- RAG pipeline instrumentation
"""

from contextlib import contextmanager
from functools import wraps
from typing import Optional, Dict, Any, Callable
import time

from core.config import settings
from core.logger import get_logger

logger = get_logger(__name__)

# Conditional imports for OpenTelemetry
_otel_available = False
_tracer = None
_meter = None

try:
    from opentelemetry import trace, metrics
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.trace import Status, StatusCode
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    _otel_available = True
except ImportError:
    logger.warning("OpenTelemetry not installed. Tracing disabled.")


def setup_telemetry(app=None) -> bool:
    """
    Configure OpenTelemetry for the application.
    
    Args:
        app: FastAPI application instance (optional)
        
    Returns:
        True if telemetry was set up, False otherwise
    """
    global _tracer, _meter
    
    if not settings.tracing_enabled:
        logger.info("Tracing disabled in settings")
        return False
    
    if not _otel_available:
        logger.warning("OpenTelemetry packages not available")
        return False
    
    try:
        # Create resource with service information
        resource = Resource.create({
            "service.name": settings.app_name,
            "service.version": "1.0.0",
            "deployment.environment": settings.app_env
        })
        
        # Setup tracing
        tracer_provider = TracerProvider(resource=resource)
        
        # Configure OTLP exporter
        otlp_exporter = OTLPSpanExporter(
            endpoint=settings.otlp_endpoint,
            insecure=True  # Use insecure for local development
        )
        
        span_processor = BatchSpanProcessor(otlp_exporter)
        tracer_provider.add_span_processor(span_processor)
        trace.set_tracer_provider(tracer_provider)
        
        _tracer = trace.get_tracer(__name__)
        
        # Setup metrics
        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(
                endpoint=settings.otlp_endpoint,
                insecure=True
            ),
            export_interval_millis=60000  # Export every 60 seconds
        )
        
        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[metric_reader]
        )
        metrics.set_meter_provider(meter_provider)
        
        _meter = metrics.get_meter(__name__)
        
        # Instrument FastAPI
        if app:
            FastAPIInstrumentor.instrument_app(app)
        
        # Instrument HTTPX (for outgoing requests)
        HTTPXClientInstrumentor().instrument()
        
        logger.info(
            "OpenTelemetry initialized",
            endpoint=settings.otlp_endpoint,
            service=settings.app_name
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to setup telemetry: {e}")
        return False


def get_tracer():
    """Get the global tracer instance."""
    global _tracer
    
    if _tracer is None and _otel_available:
        _tracer = trace.get_tracer(__name__)
    
    return _tracer


def get_meter():
    """Get the global meter instance."""
    global _meter
    
    if _meter is None and _otel_available:
        _meter = metrics.get_meter(__name__)
    
    return _meter


# ==========================================
# Tracing Decorators
# ==========================================

def traced(
    name: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None
):
    """
    Decorator to add tracing to a function.
    
    Args:
        name: Span name (defaults to function name)
        attributes: Additional span attributes
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = get_tracer()
            span_name = name or func.__name__
            
            if tracer and _otel_available:
                with tracer.start_as_current_span(span_name) as span:
                    if attributes:
                        for key, value in attributes.items():
                            span.set_attribute(key, value)
                    
                    try:
                        result = await func(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as e:
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        span.record_exception(e)
                        raise
            else:
                return await func(*args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            tracer = get_tracer()
            span_name = name or func.__name__
            
            if tracer and _otel_available:
                with tracer.start_as_current_span(span_name) as span:
                    if attributes:
                        for key, value in attributes.items():
                            span.set_attribute(key, value)
                    
                    try:
                        result = func(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as e:
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        span.record_exception(e)
                        raise
            else:
                return func(*args, **kwargs)
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


@contextmanager
def trace_span(name: str, attributes: Optional[Dict[str, Any]] = None):
    """
    Context manager for creating a trace span.
    
    Args:
        name: Span name
        attributes: Span attributes
    """
    tracer = get_tracer()
    
    if tracer and _otel_available:
        with tracer.start_as_current_span(name) as span:
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)
            try:
                yield span
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
    else:
        yield None


# ==========================================
# RAG-Specific Metrics
# ==========================================

class RAGMetrics:
    """
    RAG pipeline metrics collection.
    
    Tracks key performance indicators for the RAG system.
    """
    
    def __init__(self):
        self.meter = get_meter()
        self._setup_metrics()
    
    def _setup_metrics(self):
        """Initialize all RAG metrics."""
        if not self.meter:
            return
        
        # Query latency histogram
        self.query_latency = self.meter.create_histogram(
            name="rag.query.latency",
            description="RAG query processing latency",
            unit="ms"
        )
        
        # Retrieval metrics
        self.retrieval_count = self.meter.create_counter(
            name="rag.retrieval.count",
            description="Number of retrieval operations"
        )
        
        self.retrieved_chunks = self.meter.create_histogram(
            name="rag.retrieval.chunks",
            description="Number of chunks retrieved per query"
        )
        
        self.rerank_score = self.meter.create_histogram(
            name="rag.rerank.score",
            description="Top reranking score distribution"
        )
        
        # Generation metrics
        self.generation_tokens = self.meter.create_histogram(
            name="rag.generation.tokens",
            description="Number of tokens generated"
        )
        
        self.generation_latency = self.meter.create_histogram(
            name="rag.generation.latency",
            description="LLM generation latency",
            unit="ms"
        )
        
        # Error tracking
        self.error_count = self.meter.create_counter(
            name="rag.errors",
            description="RAG pipeline errors"
        )
        
        # Guardrail metrics
        self.guardrail_blocks = self.meter.create_counter(
            name="rag.guardrail.blocks",
            description="Queries blocked by guardrails"
        )
        
        # Evaluation metrics (RAGAS scores)
        self.eval_faithfulness = self.meter.create_histogram(
            name="rag.evaluation.faithfulness",
            description="Faithfulness score (hallucination detection)",
            unit="1"
        )
        
        self.eval_relevance = self.meter.create_histogram(
            name="rag.evaluation.relevance",
            description="Answer relevance score",
            unit="1"
        )
        
        self.eval_precision = self.meter.create_histogram(
            name="rag.evaluation.context_precision",
            description="Context precision score",
            unit="1"
        )
    
    def record_query_latency(self, latency_ms: float, query_type: str = "rag"):
        """Record query processing latency."""
        if self.meter:
            self.query_latency.record(latency_ms, {"query_type": query_type})
    
    def record_retrieval(
        self,
        chunk_count: int,
        top_score: float,
        search_type: str = "hybrid"
    ):
        """Record retrieval metrics."""
        if self.meter:
            self.retrieval_count.add(1, {"search_type": search_type})
            self.retrieved_chunks.record(chunk_count)
            self.rerank_score.record(top_score)
    
    def record_generation(self, token_count: int, latency_ms: float):
        """Record generation metrics."""
        if self.meter:
            self.generation_tokens.record(token_count)
            self.generation_latency.record(latency_ms)
    
    def record_error(self, error_type: str, component: str):
        """Record error occurrence."""
        if self.meter:
            self.error_count.add(1, {"error_type": error_type, "component": component})
    
    def record_guardrail_block(self, violation_type: str):
        """Record guardrail block."""
        if self.meter:
            self.guardrail_blocks.add(1, {"violation_type": violation_type})
            
    def record_evaluation(self, scores: Dict[str, float]):
        """Record RAGAS evaluation scores."""
        if self.meter:
            if "faithfulness" in scores:
                self.eval_faithfulness.record(scores["faithfulness"])
            if "answer_relevance" in scores:
                self.eval_relevance.record(scores["answer_relevance"])
            if "context_precision" in scores:
                self.eval_precision.record(scores["context_precision"])


# Global metrics instance
_rag_metrics: Optional[RAGMetrics] = None


def get_rag_metrics() -> RAGMetrics:
    """Get the global RAG metrics instance."""
    global _rag_metrics
    
    if _rag_metrics is None:
        _rag_metrics = RAGMetrics()
    
    return _rag_metrics


# ==========================================
# Performance Timing Utilities
# ==========================================

class Timer:
    """Simple timer for measuring execution time."""
    
    def __init__(self):
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
    
    def start(self):
        """Start the timer."""
        self.start_time = time.perf_counter()
        return self
    
    def stop(self) -> float:
        """Stop the timer and return elapsed milliseconds."""
        self.end_time = time.perf_counter()
        return self.elapsed_ms
    
    @property
    def elapsed_ms(self) -> float:
        """Get elapsed time in milliseconds."""
        if self.start_time is None:
            return 0.0
        
        end = self.end_time or time.perf_counter()
        return (end - self.start_time) * 1000
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, *args):
        self.stop()


def timed_operation(operation_name: str):
    """
    Decorator to time an operation and log results.
    
    Args:
        operation_name: Name of the operation for logging
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            with Timer() as timer:
                result = await func(*args, **kwargs)
            
            logger.debug(
                f"{operation_name} completed",
                duration_ms=round(timer.elapsed_ms, 2)
            )
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            with Timer() as timer:
                result = func(*args, **kwargs)
            
            logger.debug(
                f"{operation_name} completed",
                duration_ms=round(timer.elapsed_ms, 2)
            )
            return result
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator
