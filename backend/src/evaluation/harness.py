"""
Minimum viable eval harness.

Dataset: JSON list of cases
    {"question": "...",
     "relevant": ["policy.md", "policy.md#p3", "<substring that must appear in a retrieved chunk>"],
     "expected_answer": "optional reference answer",
     "expected_substrings": ["220 USD"],          # must appear in the final answer
     "type": "lookup|comparative|..."}

Metrics (per case and aggregated):
  retrieval : hit@k, mrr, context_recall (expected_substrings found in retrieved context)
  answer    : substring_recall, citation_rate, optional judge faithfulness / relevancy (0-1)
  latency   : retrieval_ms, total_ms
"""

from __future__ import annotations

import json
import os
import statistics
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.contracts import RetrievalRequest, RetrievedChunk
from src.core.logger import get_logger
from src.knowledge import get_knowledge_adapter
from src.services.llm.nvidia_llm_service import NvidiaLLMService, extract_json, get_llm_service

logger = get_logger(__name__)


class EvalCase(BaseModel):
    question: str
    relevant: List[str] = Field(default_factory=list)
    expected_answer: Optional[str] = None
    expected_substrings: List[str] = Field(default_factory=list)
    type: str = "lookup"


class EvalCaseResult(BaseModel):
    question: str
    type: str
    hit_at_k: bool = False
    first_hit_rank: Optional[int] = None
    reciprocal_rank: float = 0.0
    context_recall: Optional[float] = None
    answer_substring_recall: Optional[float] = None
    citation_count: int = 0
    faithfulness: Optional[float] = None
    relevancy: Optional[float] = None
    retrieval_ms: float = 0.0
    total_ms: float = 0.0
    answer: Optional[str] = None
    top_sources: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class EvalReport(BaseModel):
    cases: int
    top_k: int
    backend: str
    hit_rate: float
    mrr: float
    context_recall: Optional[float]
    answer_substring_recall: Optional[float]
    citation_rate: Optional[float]
    faithfulness: Optional[float]
    relevancy: Optional[float]
    p50_retrieval_ms: float
    p95_retrieval_ms: float
    p50_total_ms: float
    results: List[EvalCaseResult]
    by_type: Dict[str, Dict[str, float]] = Field(default_factory=dict)


def load_dataset(path: str) -> List[EvalCase]:
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [EvalCase(**c) for c in data]


def chunk_matches(chunk: RetrievedChunk, target: str) -> bool:
    t = target.strip()
    if "#p" in t:
        src, page = t.rsplit("#p", 1)
        return chunk.source == src and str(chunk.page) == page
    if chunk.source == t or chunk.document_id == t:
        return True
    return t.lower() in chunk.content.lower()


JUDGE_PROMPT = """You are grading an answer produced from evidence.
Evidence:
{context}

Question: {question}
Answer: {answer}
{reference}
Return ONLY JSON: {{"faithfulness": 0-1 (fraction of answer claims supported by the evidence),
"relevancy": 0-1 (does the answer address the question), "notes": "short"}}"""


class EvalHarness:
    def __init__(self, backend: Optional[str] = None, llm: Optional[NvidiaLLMService] = None, engine=None):
        self.adapter = get_knowledge_adapter(backend)
        self._llm = llm
        self._engine = engine

    @property
    def llm(self) -> NvidiaLLMService:
        if self._llm is None:
            self._llm = get_llm_service()
        return self._llm

    @property
    def engine(self):
        if self._engine is None:
            from src.orchestrator.engine import RetrievalEngine
            self._engine = RetrievalEngine(llm=self._llm, adapter=self.adapter)
        return self._engine

    async def _judge(self, question: str, answer: str, context: str, reference: Optional[str]) -> Dict[str, float]:
        ref = f"Reference answer: {reference}" if reference else ""
        data = await self.llm.generate_json(JUDGE_PROMPT.format(context=context[:8000], question=question, answer=answer, reference=ref),
                                            max_tokens=200, fast=True)
        return {"faithfulness": float(data.get("faithfulness", 0)), "relevancy": float(data.get("relevancy", 0))}

    async def run_case(self, case: EvalCase, top_k: int, judge: bool, answer: bool) -> EvalCaseResult:
        res = EvalCaseResult(question=case.question, type=case.type)
        started = time.perf_counter()
        try:
            r0 = time.perf_counter()
            retrieval = await self.adapter.retrieve(RetrievalRequest(query=case.question, top_k=top_k))
            res.retrieval_ms = round((time.perf_counter() - r0) * 1000, 1)
            res.top_sources = [f"{c.source}#p{c.page}" if c.page is not None else c.source for c in retrieval.chunks]
            if case.relevant:
                for rank, chunk in enumerate(retrieval.chunks, 1):
                    if any(chunk_matches(chunk, t) for t in case.relevant):
                        res.hit_at_k, res.first_hit_rank, res.reciprocal_rank = True, rank, 1.0 / rank
                        break
            if case.expected_substrings:
                ctx = (retrieval.context or " ".join(c.content for c in retrieval.chunks)).lower()
                found = sum(1 for s in case.expected_substrings if s.lower() in ctx)
                res.context_recall = found / len(case.expected_substrings)
            if answer or judge:
                ans = await self.engine.answer(case.question, top_k=top_k)
                res.answer = ans.text
                res.citation_count = len(ans.citations)
                if case.expected_substrings:
                    found = sum(1 for s in case.expected_substrings if s.lower() in ans.text.lower())
                    res.answer_substring_recall = found / len(case.expected_substrings)
                if judge and ans.evidence:
                    scores = await self._judge(case.question, ans.text, retrieval.context or "", case.expected_answer)
                    res.faithfulness, res.relevancy = scores["faithfulness"], scores["relevancy"]
        except Exception as exc:
            res.error = str(exc)
            logger.warning("Eval case failed", question=case.question[:80], error=str(exc))
        res.total_ms = round((time.perf_counter() - started) * 1000, 1)
        return res

    async def run(self, dataset: List[EvalCase], top_k: int = 8, judge: bool = False, answer: Optional[bool] = None) -> EvalReport:
        answer = judge if answer is None else answer
        results = [await self.run_case(c, top_k, judge, answer) for c in dataset]
        return self.summarize(results, top_k)

    def summarize(self, results: List[EvalCaseResult], top_k: int) -> EvalReport:
        def mean(values: List[Optional[float]]) -> Optional[float]:
            vals = [v for v in values if v is not None]
            return round(statistics.fmean(vals), 4) if vals else None

        def pct(values: List[float], p: float) -> float:
            if not values:
                return 0.0
            s = sorted(values)
            idx = min(len(s) - 1, max(0, int(round(p * (len(s) - 1)))))
            return round(s[idx], 1)

        graded = [r for r in results if r.error is None]
        with_relevant = [r for r in graded if r.first_hit_rank is not None or r.reciprocal_rank == 0.0]
        answered = [r for r in graded if r.answer is not None]
        by_type: Dict[str, Dict[str, float]] = {}
        for t in sorted({r.type for r in graded}):
            group = [r for r in graded if r.type == t]
            by_type[t] = {"cases": len(group), "hit_rate": round(sum(r.hit_at_k for r in group) / len(group), 4),
                          "mrr": round(sum(r.reciprocal_rank for r in group) / len(group), 4)}
        return EvalReport(
            cases=len(results), top_k=top_k, backend=self.adapter.name,
            hit_rate=round(sum(r.hit_at_k for r in graded) / len(graded), 4) if graded else 0.0,
            mrr=round(sum(r.reciprocal_rank for r in graded) / len(graded), 4) if graded else 0.0,
            context_recall=mean([r.context_recall for r in graded]),
            answer_substring_recall=mean([r.answer_substring_recall for r in answered]),
            citation_rate=mean([1.0 if r.citation_count > 0 else 0.0 for r in answered]) if answered else None,
            faithfulness=mean([r.faithfulness for r in answered]),
            relevancy=mean([r.relevancy for r in answered]),
            p50_retrieval_ms=pct([r.retrieval_ms for r in graded], 0.5),
            p95_retrieval_ms=pct([r.retrieval_ms for r in graded], 0.95),
            p50_total_ms=pct([r.total_ms for r in graded], 0.5),
            results=results, by_type=by_type,
        )
