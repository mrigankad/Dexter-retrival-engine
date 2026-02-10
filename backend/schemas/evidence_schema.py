"""
Evidence Schema - Structured evidence types for the reasoning engine.

Defines:
- EvidenceChunk: Individual piece of evidence
- EvidenceBlock: Assembled evidence for a sub-query
- EvidenceAggregate: Combined evidence across all sub-queries
- TracedAnswer: Final answer with full provenance chain
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum
from datetime import datetime


class EvidenceType(str, Enum):
    """Types of evidence."""
    TEXT = "text"
    TABLE = "table"
    CHART = "chart"
    IMAGE = "image"
    COMPUTED = "computed"  # Derived from multiple sources


class EvidenceQuality(str, Enum):
    """Quality levels for evidence."""
    HIGH = "high"          # Direct match, high rerank score
    MEDIUM = "medium"      # Partial match
    LOW = "low"            # Indirect/inferred
    RECOVERED = "recovered"  # From feedback loop


@dataclass
class EvidenceChunk:
    """A single piece of evidence with provenance."""
    chunk_id: str
    content: str
    content_type: EvidenceType
    source_document: str
    page: int
    score: float
    rerank_score: Optional[float] = None
    quality: EvidenceQuality = EvidenceQuality.MEDIUM
    document_id: Optional[str] = None
    section_title: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def citation(self) -> str:
        """Generate page citation string."""
        return f"[Page {self.page}]"

    def to_dict(self) -> Dict:
        return {
            "chunk_id": self.chunk_id,
            "content_type": self.content_type.value,
            "source": self.source_document,
            "page": self.page,
            "score": self.score,
            "quality": self.quality.value,
            "citation": self.citation,
        }


@dataclass
class EvidenceBlock:
    """Evidence assembled for a single sub-query."""
    sub_query: str
    sub_query_id: str
    chunks: List[EvidenceChunk] = field(default_factory=list)
    compressed_text: str = ""
    compression_ratio: float = 0.0
    retrieval_time_ms: float = 0.0
    is_empty: bool = False

    @property
    def total_score(self) -> float:
        """Average evidence quality score."""
        if not self.chunks:
            return 0.0
        return sum(c.score for c in self.chunks) / len(self.chunks)

    @property
    def citations(self) -> List[str]:
        """All unique citations in this block."""
        return list(set(c.citation for c in self.chunks))

    def to_context_string(self) -> str:
        """Convert to context string for LLM."""
        if self.compressed_text:
            return f"### Evidence for: '{self.sub_query}'\n{self.compressed_text}"
        parts = []
        for c in self.chunks:
            parts.append(f"{c.citation} {c.content}")
        return f"### Evidence for: '{self.sub_query}'\n" + "\n".join(parts)


@dataclass
class EvidenceAggregate:
    """Combined evidence from all sub-queries in a plan."""
    query: str
    plan_reasoning: str
    blocks: List[EvidenceBlock] = field(default_factory=list)
    synthesis_strategy: str = "summary"
    total_chunks: int = 0
    total_unique_pages: int = 0
    empty_blocks: int = 0
    recovered_blocks: int = 0
    execution_time_ms: float = 0.0

    def to_context_string(self) -> str:
        """Assemble full context for the synthesis engine."""
        parts = []
        for i, block in enumerate(self.blocks, 1):
            if block.is_empty:
                parts.append(
                    f"### Evidence {i} (MISSING): '{block.sub_query}'\n"
                    "[No evidence found for this query]"
                )
            else:
                parts.append(f"### Evidence {i}: '{block.sub_query}'\n{block.compressed_text}")
        return "\n\n".join(parts)

    @property
    def coverage_ratio(self) -> float:
        """Fraction of sub-queries with evidence."""
        if not self.blocks:
            return 0.0
        filled = sum(1 for b in self.blocks if not b.is_empty)
        return filled / len(self.blocks)

    def get_all_sources(self) -> List[Dict]:
        """Get deduplicated source list across all blocks."""
        sources = []
        seen = set()
        for block in self.blocks:
            for chunk in block.chunks:
                key = (chunk.document_id, chunk.page, chunk.chunk_id)
                if key not in seen:
                    seen.add(key)
                    sources.append(chunk.to_dict())
        return sources


@dataclass
class TracedAnswer:
    """Final answer with complete provenance chain."""
    query: str
    response: str
    confidence: float
    citations: List[str]
    missing_info: List[str]
    evidence_aggregate: Optional[EvidenceAggregate] = None
    plan: Optional[Dict] = None
    synthesis_strategy: str = "summary"
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    model_used: str = ""
    latency_ms: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "query": self.query,
            "response": self.response,
            "confidence": self.confidence,
            "citations": self.citations,
            "missing_info": self.missing_info,
            "synthesis_strategy": self.synthesis_strategy,
            "timestamp": self.timestamp,
            "model_used": self.model_used,
            "latency_ms": self.latency_ms,
            "plan": self.plan,
            "evidence_coverage": (
                self.evidence_aggregate.coverage_ratio
                if self.evidence_aggregate else None
            ),
            "total_sources": (
                len(self.evidence_aggregate.get_all_sources())
                if self.evidence_aggregate else 0
            ),
        }
