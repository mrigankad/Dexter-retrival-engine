"""Rank fusion and de-duplication helpers."""

from __future__ import annotations

import hashlib
from typing import Dict, Iterable, List, Sequence

from src.contracts import RetrievedChunk


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[RetrievedChunk]], k: int = 60, weights: Sequence[float] | None = None,
) -> List[RetrievedChunk]:
    """Fuse several ranked lists (e.g. per sub-query / per backend) with RRF.

    Each chunk's fused score = sum_i w_i / (k + rank_i). The returned chunk
    objects are copies of the first occurrence with ``score`` replaced by the
    fused score and the original score stored in ``metadata['pre_fusion_score']``.
    """
    weights = list(weights) if weights else [1.0] * len(ranked_lists)
    scores: Dict[str, float] = {}
    first: Dict[str, RetrievedChunk] = {}
    for weight, ranked in zip(weights, ranked_lists):
        for rank, chunk in enumerate(ranked):
            key = chunk.id
            scores[key] = scores.get(key, 0.0) + weight / (k + rank + 1)
            if key not in first:
                first[key] = chunk
    fused: List[RetrievedChunk] = []
    for key, score in sorted(scores.items(), key=lambda kv: kv[1], reverse=True):
        chunk = first[key].model_copy(deep=True)
        chunk.metadata["pre_fusion_score"] = first[key].score
        chunk.score = score
        fused.append(chunk)
    return fused


def _fingerprint(text: str, chars: int = 240) -> str:
    normalized = " ".join(text.lower().split())[:chars]
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def dedupe_chunks(chunks: Iterable[RetrievedChunk]) -> List[RetrievedChunk]:
    """Drop exact and near-duplicate chunks (same id or same leading text)."""
    seen_ids: set = set()
    seen_fp: set = set()
    out: List[RetrievedChunk] = []
    for chunk in chunks:
        fp = _fingerprint(chunk.content)
        if chunk.id in seen_ids or fp in seen_fp:
            continue
        seen_ids.add(chunk.id)
        seen_fp.add(fp)
        out.append(chunk)
    return out
