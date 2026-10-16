import pytest

from src.contracts import Evidence, Intent
from src.orchestrator.router import QueryRouter, classify_query_type, extract_keywords
from src.orchestrator.synthesizer import assess_confidence, resolve_citations


@pytest.mark.parametrize("query,intent,qtype", [
    ("hello there", Intent.CHAT, "chat"),
    ("Thanks!", Intent.CHAT, "chat"),
    ("send this report to finance", Intent.ACTION, "lookup"),
    ("What does the policy say about hotels?", Intent.KNOWLEDGE, "lookup"),
    ("Compare FY24 and FY25 revenue", Intent.KNOWLEDGE, "comparative"),
    ("why did margins fall in Q3", Intent.KNOWLEDGE, "causal"),
    ("Summarize all key points of the annual report", Intent.KNOWLEDGE, "aggregation"),
])
def test_rule_router(query, intent, qtype):
    d = QueryRouter(use_llm=False).route_rules(query)
    assert d is not None
    assert d.intent == intent
    assert d.query_type == qtype


def test_classify_and_keywords():
    assert classify_query_type("trend of revenue over time") == "temporal"
    kws = extract_keywords("What is the EBITDA margin for FY2024?")
    assert "ebitda" in kws and "fy2024" in kws and "what" not in kws


@pytest.mark.asyncio
async def test_llm_router_fallback_when_llm_fails():
    class Broken:
        async def generate_json(self, *a, **k):
            raise RuntimeError("down")
    d = await QueryRouter(llm=Broken()).route("hotels")   # single word → rules undecided → LLM → fallback
    assert d.intent == Intent.KNOWLEDGE
    assert d.method in ("fallback", "rules")


def _ev(n: int, rerank: float | None = 0.7) -> Evidence:
    return Evidence(id=f"ev_{n}", source_name="s.pdf", snippet="x", score=0.5, rerank_score=rerank)


def test_resolve_citations_strips_unknown_markers():
    text, cites = resolve_citations("A fact [1]. Another [2] and bogus [7]. Repeat [1].", [_ev(1), _ev(2)])
    assert "[7]" not in text and "[1]" in text and "[2]" in text
    assert [c.marker for c in cites] == ["[1]", "[2]"]
    assert cites[0].evidence_id == "ev_1"


def test_confidence_levels():
    ev = [_ev(1), _ev(2)]
    _, cites = resolve_citations("Fact [1]. Fact [2].", ev)
    assert assess_confidence(ev, cites, "Fact [1]. Fact [2].").value == "high"
    assert assess_confidence(ev, [], "no citations").value == "low"
    assert assess_confidence([], [], "anything").value == "low"
    assert assess_confidence(ev, cites, "The evidence does not contain this [1]").value == "low"
