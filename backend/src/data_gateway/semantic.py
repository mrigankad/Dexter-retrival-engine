"""Semantic business layer: entities, metrics, synonyms, verified queries; relevant-schema selection."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .models import SchemaCatalog, SemanticEntity, SemanticModel, TableInfo, VerifiedQuery
from .policy import normalize_question

_WORD = re.compile(r"[a-z0-9]+")


def _terms(text: str) -> set:
    return {w for w in _WORD.findall(text.lower()) if len(w) > 2}


def match_verified(model: Optional[SemanticModel], question: str) -> Optional[VerifiedQuery]:
    if model is None:
        return None
    q = normalize_question(question)
    for vq in model.verified_queries:
        pattern = vq.question_pattern.strip()
        if not pattern:
            continue
        if normalize_question(pattern) == q:
            return vq
        try:
            if re.fullmatch(pattern, question.strip(), flags=re.IGNORECASE) or re.search(pattern, question, flags=re.IGNORECASE) and len(pattern) > 12:
                return vq
        except re.error:
            continue
    return None


def rank_tables(catalog: SchemaCatalog, model: Optional[SemanticModel], question: str, k: int = 5) -> List[Tuple[TableInfo, float]]:
    """Score tables by lexical overlap between the question and table/column/entity names + synonyms."""
    q = _terms(question)
    scored: List[Tuple[TableInfo, float]] = []
    entity_by_table: Dict[str, SemanticEntity] = {}
    if model is not None:
        for e in model.entities:
            entity_by_table[e.source.lower()] = e
    for t in catalog.tables:
        vocab = _terms(t.name) | {w for c in t.columns for w in _terms(c.name)}
        ent = entity_by_table.get(t.qualified.lower()) or entity_by_table.get(t.name.lower())
        bonus = 0.0
        if ent is not None:
            vocab |= _terms(ent.name) | _terms(ent.description)
            for term, syns in ent.synonyms.items():
                vocab |= _terms(term)
                for s in syns:
                    if _terms(s) & q:
                        bonus += 2.0
            vocab |= {w for m in ent.metrics for w in _terms(m)} | {w for d in ent.dimensions for w in _terms(d)}
        overlap = len(vocab & q)
        # singular/plural tolerance
        overlap += sum(1 for w in q if any(v.startswith(w[:-1]) and len(w) > 4 for v in vocab))
        score = overlap + bonus
        if score > 0:
            scored.append((t, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    # pull in tables referenced by foreign keys of the top hits (joins)
    chosen = [t for t, _ in scored[:k]]
    names = {t.name.lower() for t in chosen}
    for t in list(chosen):
        for c in t.columns:
            if c.foreign_key:
                ref = c.foreign_key.split(".")[0].lower()
                other = catalog.table(ref)
                if other is not None and other.name.lower() not in names and len(chosen) < k + 3:
                    chosen.append(other)
                    names.add(other.name.lower())
    score_by_name = {t.qualified: sc for t, sc in scored}
    return [(t, score_by_name.get(t.qualified, 0.0)) for t in chosen]


def schema_context(tables: List[TableInfo], model: Optional[SemanticModel], max_columns: int = 40) -> str:
    """Compact DDL-like description of only the relevant tables, plus approved semantics."""
    lines: List[str] = []
    entity_by_table = {e.source.lower(): e for e in (model.entities if model else [])}
    for t in tables:
        cols = []
        for c in t.columns[:max_columns]:
            flag = " PK" if c.primary_key else (f" FK->{c.foreign_key}" if c.foreign_key else "")
            cols.append(f"{c.name} {c.type}{flag}")
        lines.append(f"TABLE {t.qualified} ({', '.join(cols)})")
        ent = entity_by_table.get(t.qualified.lower()) or entity_by_table.get(t.name.lower())
        if ent is not None:
            if ent.description:
                lines.append(f"  -- {ent.name}: {ent.description}")
            for name, col in ent.dimensions.items():
                lines.append(f"  -- dimension {name} = {col}")
            for name, expr in ent.metrics.items():
                lines.append(f"  -- metric {name} = {expr}")
            for name, join in ent.relationships.items():
                lines.append(f"  -- join {name}: {join}")
            for term, syns in ent.synonyms.items():
                lines.append(f"  -- '{term}' is also called: {', '.join(syns)}")
    if model and model.glossary:
        lines.append("GLOSSARY: " + "; ".join(f"{k} = {v}" for k, v in list(model.glossary.items())[:20]))
    return "\n".join(lines)


def example_context(model: Optional[SemanticModel], question: str, k: int = 3) -> str:
    if model is None or not model.verified_queries:
        return ""
    q = _terms(question)
    ranked = sorted(model.verified_queries, key=lambda v: len(_terms(v.question_pattern) & q), reverse=True)[:k]
    return "\n\n".join(f"Q: {v.question_pattern}\nSQL: {v.sql}" for v in ranked if _terms(v.question_pattern) & q)
