import json
import uuid
from pathlib import Path

import pytest

from src.contracts import IngestionJob, Intent, RetrievalFilters, RetrievalRequest

SAMPLES = Path(__file__).parent.parent / "samples"


@pytest.mark.asyncio
async def test_ingest_and_hybrid_retrieve(indexed_policy):
    from src.knowledge import get_knowledge_adapter
    from src.infrastructure.vector_store import get_qdrant_store

    assert await get_qdrant_store().count(document_id=indexed_policy) >= 3
    adapter = get_knowledge_adapter("local")
    r = await adapter.retrieve(RetrievalRequest(query="hotel limit per night in a Tier 1 city", top_k=3))
    assert r.chunks and r.backend == "local"
    assert any("220" in c.content for c in r.chunks)
    assert r.chunks[0].rerank_score is not None
    assert r.context.startswith("[1] policy.md")
    # document scoping
    r2 = await adapter.retrieve(RetrievalRequest(query="hotel", filters=RetrievalFilters(document_ids=["missing"])))
    assert r2.is_empty
    # multi-query fusion path
    r3 = await adapter.retrieve(RetrievalRequest(query="hotel cap", alternate_queries=["nightly hotel limit"], top_k=3))
    assert r3.chunks and len(r3.executed_queries) == 2


@pytest.mark.asyncio
async def test_failed_parse_marks_document_failed(services, tmp_path):
    from sqlalchemy import select
    from src.infrastructure.database import Document, session_scope
    from src.ingestion import get_ingestion_pipeline

    did = str(uuid.uuid4())
    bad = tmp_path / "empty.txt"
    bad.write_text("  ")
    async with session_scope() as s:
        s.add(Document(id=uuid.UUID(did), filename="empty.txt", file_type="txt", file_size=1))
    result = await get_ingestion_pipeline().process(IngestionJob(document_id=did, file_path=str(bad), filename="empty.txt"))
    assert result.status == "failed" and "No extractable text" in (result.error or "")
    async with session_scope() as s:
        doc = await s.scalar(select(Document).where(Document.id == uuid.UUID(did)))
        assert doc.status == "failed" and doc.error_message


@pytest.mark.asyncio
async def test_engine_streams_events_with_validated_citations(indexed_policy, services):
    fake_llm, _, _ = services
    from src.orchestrator import RetrievalEngine
    from src.services.traces import list_traces, persist_trace

    engine = RetrievalEngine(llm=fake_llm, trace_sink=persist_trace)
    events = []
    async for ev in engine.answer_stream("What is the hotel limit per night in a Tier 1 city?", session_id="s1"):
        events.append(ev)
    names = [e.event for e in events]
    assert names[0] == "progress" and "evidence" in names and "sources" in names and names[-1] == "done"
    assert "answer_delta" in names and "token" not in names
    done = events[-1].data
    assert done["confidence"] == "high" and [c["marker"] for c in done["citations"]] == ["[1]", "[2]"]
    answer = engine.last_answer
    assert "[9]" not in answer.text and "Removed citations" in " ".join(answer.warnings)
    assert answer.intent == Intent.KNOWLEDGE and answer.evidence and answer.trace_id
    traces = await list_traces()
    assert traces and traces[0]["intent"] == "KNOWLEDGE" and traces[0]["evidence_count"] >= 1


@pytest.mark.asyncio
async def test_engine_chat_action_and_no_documents(services):
    fake_llm, _, _ = services
    from src.orchestrator import RetrievalEngine
    engine = RetrievalEngine(llm=fake_llm)
    chat = await engine.answer("hello there")
    assert chat.intent == Intent.CHAT and chat.text.startswith("Hi!")
    action = await engine.answer("send this report to finance")
    assert action.intent == Intent.ACTION and "can't perform actions" in action.text
    nodocs = await engine.answer("What does the policy say about hotels?", has_documents=False)
    assert "No documents have been indexed" in nodocs.text and nodocs.confidence.value == "low"


@pytest.mark.asyncio
async def test_engine_multi_hop_plan_and_rag_disabled(indexed_policy, services):
    fake_llm, _, _ = services
    from src.orchestrator import RetrievalEngine
    engine = RetrievalEngine(llm=fake_llm)
    events = [e async for e in engine.answer_stream("Compare the hotel limit for Tier 1 cities versus other cities")]
    planning = [e for e in events if e.event == "progress" and e.data["stage"] == "planning"]
    assert planning and len(planning[0].data["detail"]["sub_questions"]) == 2
    assert engine.last_answer.evidence
    trace_calls = [c for c in engine.last_answer.usage if c]  # usage recorded
    assert engine.last_answer.usage["llm_calls"] >= 2
    direct = await engine.answer("What is the hotel limit?", use_rag=False)
    assert direct.intent == Intent.CHAT


@pytest.mark.asyncio
async def test_engine_with_mock_backend_and_fallback(services, monkeypatch):
    fake_llm, _, _ = services
    from src.knowledge import get_knowledge_adapter
    from src.orchestrator import RetrievalEngine
    from src.orchestrator.executor import PlanExecutor

    mock = get_knowledge_adapter("mock")
    mock.add("Hotel stays are capped at 220 USD per night in Tier 1 cities.", source="policy.pdf", page=2)
    engine = RetrievalEngine(llm=fake_llm, adapter=mock)
    ans = await engine.answer("What is the hotel limit per night in a Tier 1 city?")
    assert ans.evidence[0].backend == "mock" and ans.citations

    class Failing(type(mock)):
        name = "failing"
        async def retrieve(self, request):
            raise RuntimeError("backend down")
    executor = PlanExecutor(adapter=Failing(), fallback=mock)
    engine2 = RetrievalEngine(llm=fake_llm, adapter=Failing(), executor=executor)
    ans2 = await engine2.answer("What is the hotel limit per night in a Tier 1 city?")
    assert ans2.evidence and ans2.evidence[0].backend == "mock"


@pytest.mark.asyncio
async def test_eval_harness(indexed_policy, services):
    fake_llm, _, _ = services
    from src.evaluation import EvalCase, EvalHarness
    cases = [EvalCase(question="What is the hotel limit per night in a Tier 1 city?", relevant=["policy.md"], expected_substrings=["220"]),
             EvalCase(question="When must claims be submitted?", relevant=["30 days"], expected_substrings=["30 days"], type="lookup")]
    report = await EvalHarness(backend="local", llm=fake_llm).run(cases, top_k=4, judge=False, answer=True)
    assert report.cases == 2 and report.hit_rate == 1.0 and report.mrr > 0
    assert report.context_recall == 1.0
    assert report.citation_rate is not None
