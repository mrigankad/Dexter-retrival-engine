"""
BM25-style sparse encoder with no model download.

Produces Qdrant sparse vectors: token -> uint32 index (CRC32 hash), value =
BM25 term-frequency saturation. IDF weighting is applied by Qdrant itself when
the sparse vector is configured with ``Modifier.IDF`` (so the encoder stays
stateless and identical for ingestion and query time).

This is the same scheme fastembed's ``Qdrant/bm25`` uses, re-implemented in
~100 lines so the engine has no ONNX runtime dependency.
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass
from typing import Dict, Iterable, List

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.'][a-z0-9]+)*")

_STOPWORDS = frozenset("""
a an and are as at be but by for from has have he her his if in into is it its of on or
she that the their them there these they this to was we were what when where which who
will with would you your our about above after again against all am any because been
before being below between both can could did do does doing down during each few further
had having here how i me more most my myself no nor not off once only other out over own
same so some such than then through too under until up very why yourself yourselves
""".split())


def _stem(token: str) -> str:
    """Very light suffix stripping (good enough for lexical matching)."""
    if len(token) <= 4:
        return token
    for suffix in ("ations", "ation", "ingly", "ings", "ness", "ment", "ing", "ies", "ers", "ed", "es", "ly", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            if suffix == "es" and not token.endswith(("sses", "shes", "ches", "xes", "zes")):
                continue   # "prices" -> handled by the "s" rule -> "price"
            base = token[: -len(suffix)]
            if suffix == "ies":
                return base + "y"
            return base
    return token


def tokenize(text: str) -> List[str]:
    tokens = _TOKEN_RE.findall(text.lower())
    return [_stem(t) for t in tokens if t not in _STOPWORDS and len(t) > 1]


def token_id(token: str) -> int:
    return zlib.crc32(token.encode("utf-8")) & 0xFFFFFFFF


@dataclass
class SparseVectorData:
    indices: List[int]
    values: List[float]

    def is_empty(self) -> bool:
        return not self.indices


class SparseEncoder:
    """Stateless BM25 term-weight encoder."""

    def __init__(self, k1: float = 1.2, b: float = 0.75, avg_doc_len: float = 256.0):
        self.k1 = k1
        self.b = b
        self.avg_doc_len = avg_doc_len

    def encode_document(self, text: str) -> SparseVectorData:
        tokens = tokenize(text)
        if not tokens:
            return SparseVectorData([], [])
        counts: Dict[int, int] = {}
        for tok in tokens:
            tid = token_id(tok)
            counts[tid] = counts.get(tid, 0) + 1
        doc_len = len(tokens)
        norm = self.k1 * (1.0 - self.b + self.b * doc_len / self.avg_doc_len)
        indices = sorted(counts)
        values = [(counts[i] * (self.k1 + 1.0)) / (counts[i] + norm) for i in indices]
        return SparseVectorData(indices, values)

    def encode_documents(self, texts: Iterable[str]) -> List[SparseVectorData]:
        return [self.encode_document(t) for t in texts]

    def encode_query(self, text: str) -> SparseVectorData:
        tokens = tokenize(text)
        if not tokens:
            return SparseVectorData([], [])
        ids = sorted({token_id(t) for t in tokens})
        return SparseVectorData(ids, [1.0] * len(ids))
