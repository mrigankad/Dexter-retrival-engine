"""
Assemble numbered evidence context for the synthesizer.

Each chunk becomes ``[n] source, p.X (section)`` + text. The synthesizer is
instructed to cite with ``[n]`` and the markers are resolved back to evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence

from src.contracts import Evidence, RetrievedChunk
from src.core.config import settings

from .fusion import dedupe_chunks


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@dataclass
class BuiltContext:
    text: str
    evidence: List[Evidence] = field(default_factory=list)
    chunks: List[RetrievedChunk] = field(default_factory=list)
    tokens: int = 0
    truncated: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.evidence


class ContextBuilder:
    def __init__(self, max_tokens: int | None = None):
        self.max_tokens = max_tokens or settings.max_context_tokens

    def build(self, chunks: Sequence[RetrievedChunk], max_tokens: int | None = None) -> BuiltContext:
        budget = max_tokens or self.max_tokens
        parts: List[str] = []
        evidence: List[Evidence] = []
        kept: List[RetrievedChunk] = []
        used = 0
        truncated = False
        for chunk in dedupe_chunks(chunks):
            n = len(evidence) + 1
            tokens = estimate_tokens(chunk.content) + 12
            if used + tokens > budget:
                truncated = True
                if not evidence:
                    # Always include at least one chunk, trimmed to the budget.
                    chunk = chunk.model_copy(update={"content": chunk.content[: budget * 4]})
                    tokens = budget
                else:
                    break
            ev = Evidence.from_chunk(n, chunk)
            header = f"[{n}] {chunk.source}"
            if chunk.page is not None:
                header += f", p.{chunk.page}"
            if chunk.section_path:
                header += f" ({' > '.join(chunk.section_path[-2:])})"
            if chunk.content_type and chunk.content_type != "text":
                header += f" [{chunk.content_type}]"
            parts.append(f"{header}\n{chunk.content.strip()}")
            evidence.append(ev)
            kept.append(chunk)
            used += tokens
        return BuiltContext(text="\n\n---\n\n".join(parts), evidence=evidence, chunks=kept, tokens=used, truncated=truncated)
