"""
Typed contracts shared across the engine.

Every layer (API, orchestrator, knowledge adapters, ingestion) speaks these
models so that a retrieval backend can be swapped (local Qdrant, Foundry IQ,
mock) without touching callers.
"""

from .common import Intent, Confidence, ContentType, ChunkLevel
from .retrieval import (
    RetrievalFilters,
    RetrievalRequest,
    RetrievedChunk,
    RetrievalResult,
    ReasoningEffort,
)
from .evidence import Evidence, EvidenceLocator, Citation
from .plan import PlanStep, QueryPlan
from .answer import Answer, AnswerBlock, TraceRecord, ToolCallRecord
from .events import (
    StreamEvent,
    ProgressEvent,
    EvidenceEvent,
    AnswerDeltaEvent,
    DoneEvent,
    ErrorEvent,
    WarningEvent,
)
from .ingestion import ParsedPage, ParsedDocument, Chunk, IngestionJob, IngestionResult

__all__ = [
    "Intent", "Confidence", "ContentType", "ChunkLevel",
    "RetrievalFilters", "RetrievalRequest", "RetrievedChunk", "RetrievalResult", "ReasoningEffort",
    "Evidence", "EvidenceLocator", "Citation",
    "PlanStep", "QueryPlan",
    "Answer", "AnswerBlock", "TraceRecord", "ToolCallRecord",
    "StreamEvent", "ProgressEvent", "EvidenceEvent", "AnswerDeltaEvent", "DoneEvent", "ErrorEvent", "WarningEvent",
    "ParsedPage", "ParsedDocument", "Chunk", "IngestionJob", "IngestionResult",
]
