import pytest

from fakes import FakeLLM
from src.contracts import RetrievalRequest
from src.core.config import settings


@pytest.mark.asyncio
async def test_summary_chunk_indexed_and_used_for_overview_questions(indexed_policy, services):
    from src.infrastructure.vector_store import get_qdrant_store
    from src.knowledge import get_knowledge_adapter
    chunks = await get_qdrant_store().get_document_chunks(indexed_policy)
    summaries = [c for c in chunks if c.metadata.get("chunk_level") == "document_summary"]
    assert len(summaries) == 1 and summaries[0].chunk_index == 0
    assert "Overview of document 'Acme Corp Travel and Expense Policy'" in summaries[0].content
    assert "Reimbursement Limits" in summaries[0].content

    adapter = get_knowledge_adapter("local")
    r = await adapter.retrieve(RetrievalRequest(query="Give me an overview of the whole document", top_k=3, include_summaries=True))
    assert any(c.metadata.get("chunk_level") == "document_summary" for c in r.chunks)

    # the executor turns aggregation questions into summary-inclusive retrieval
    from src.orchestrator import RetrievalEngine
    fake_llm, _, _ = services
    engine = RetrievalEngine(llm=fake_llm)
    answer = await engine.answer("Summarize all the key points of the travel policy document")
    assert answer.evidence and any("Overview of document" in e.snippet for e in answer.evidence)


@pytest.mark.asyncio
async def test_relevance_gate_rewrites_weak_queries(indexed_policy, services, monkeypatch):
    from src.retrieval import HybridRetriever
    llm = FakeLLM(responses={"Rewrite the search query": "hotel nightly cap for Tier 1 cities"})
    retriever = HybridRetriever(llm=llm)
    monkeypatch.setattr(settings, "relevance_gate_threshold", 0.5)
    # a vague query gets a low lexical rerank score → gate fires → rewritten query finds the hotel cap
    results = await retriever.retrieve("accommodation ceiling metropolis", top_k=3)
    assert retriever.last_trace["gated"] and retriever.last_trace["rewritten"] == "hotel nightly cap for Tier 1 cities"
    assert retriever.last_trace["attempts"] == 2
    assert any("220" in c.content for c in results) and all(c.metadata.get("adaptive_retry") for c in results)
    assert llm.calls and "Rewrite the search query" in llm.calls[0]["messages"][-1]["content"]

    # a strong query passes the gate without a rewrite
    llm.calls.clear()
    results = await retriever.retrieve("hotel limit per night in a Tier 1 city", top_k=3)
    assert not retriever.last_trace["gated"] and not llm.calls and any("220" in c.content for c in results)

    # gate disabled
    monkeypatch.setattr(settings, "adaptive_retrieval_enabled", False)
    await retriever.retrieve("accommodation ceiling metropolis", top_k=3)
    assert retriever.last_trace["attempts"] == 1


@pytest.mark.asyncio
async def test_engine_emits_otel_spans(indexed_policy, services, monkeypatch):
    otel_sdk = pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from src.core import telemetry
    from src.orchestrator import RetrievalEngine

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    telemetry.set_tracer_for_tests(provider.get_tracer("test"))
    try:
        fake_llm, _, _ = services
        answer = await RetrievalEngine(llm=fake_llm).answer("What is the hotel limit per night in a Tier 1 city?")
        spans = {s.name: s for s in exporter.get_finished_spans()}
        assert {"bodham.answer", "bodham.route", "bodham.retrieve", "bodham.synthesize"} <= set(spans)
        root = spans["bodham.answer"].attributes
        assert root["bodham.intent"] == "KNOWLEDGE" and root["bodham.confidence"] == answer.confidence.value
        assert root["gen_ai.operation.name"] == "invoke_agent" and root["bodham.trace_id"] == answer.trace_id
        retrieve = spans["bodham.retrieve"].attributes
        assert retrieve["bodham.evidence_count"] == len(answer.evidence) and retrieve["gen_ai.operation.name"] == "retrieval"
        assert len(retrieve["bodham.chunk_ids"]) == len(answer.evidence)
        assert spans["bodham.synthesize"].attributes["gen_ai.usage.output_tokens"] > 0
        assert spans["bodham.route"].parent.span_id == spans["bodham.answer"].context.span_id
    finally:
        telemetry.set_tracer_for_tests(None)


def test_otlp_exporter_factory_http(monkeypatch):
    pytest.importorskip("opentelemetry.exporter.otlp.proto.http.trace_exporter")
    from src.core import telemetry
    monkeypatch.setattr(settings, "otlp_protocol", "http")
    monkeypatch.setattr(settings, "otlp_endpoint", "https://cloud.langfuse.com/api/public/otel/v1/traces")
    monkeypatch.setattr(settings, "otlp_headers", "Authorization=Basic abc, x-langfuse-ingestion-version=4")
    exporter = telemetry._make_span_exporter()
    assert exporter._endpoint.endswith("/otel/v1/traces")

    def find_headers(obj, depth=0):
        """Locate the header mapping wherever this SDK version keeps it (exporter, client or session)."""
        if depth > 3 or obj is None:
            return None
        for value in vars(obj).values() if hasattr(obj, "__dict__") else []:
            if hasattr(value, "get") and hasattr(value, "keys") and "Authorization" in value:
                return value
            found = find_headers(value, depth + 1)
            if found is not None:
                return found
        return None

    headers = find_headers(exporter)
    assert headers is not None, "exporter did not receive the configured headers"
    assert headers.get("Authorization") == "Basic abc" and headers.get("x-langfuse-ingestion-version") == "4"
    assert telemetry._parse_headers("a=1, b = x=y") == {"a": "1", "b": "x=y"}
