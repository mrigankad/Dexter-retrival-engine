import json

import httpx
import pytest

from src.contracts import RetrievalFilters, RetrievalRequest
from src.knowledge import FoundryIQAdapter, FoundryIQError, MockKnowledgeAdapter


@pytest.mark.asyncio
async def test_mock_adapter_scores_by_overlap_and_filters():
    m = MockKnowledgeAdapter()
    m.add("The reimbursement policy allows 500 USD per trip.", source="policy.pdf", document_id="d1", page=3)
    m.add("Cats are mammals.", source="cats.txt", document_id="d2")
    r = await m.retrieve(RetrievalRequest(query="what is the reimbursement policy", top_k=5))
    assert r.chunks[0].source == "policy.pdf" and r.chunks[0].page == 3 and r.backend == "mock"
    assert "[1] policy.pdf" in r.context
    r2 = await m.retrieve(RetrievalRequest(query="reimbursement", filters=RetrievalFilters(document_ids=["d2"])))
    assert r2.is_empty


def test_foundry_request_body_and_headers():
    a = FoundryIQAdapter(endpoint="https://svc.search.windows.net/", api_key="k", knowledge_base="kb", knowledge_source="ks")
    body = a.build_request_body(RetrievalRequest(query="why", reasoning_effort="medium",
                                                 filters=RetrievalFilters(tenant_id="t1", document_ids=["a", "b"], metadata={"entra_token": "tok"})))
    assert body["outputMode"] == "extractiveData"
    assert body["retrievalReasoningEffort"] == {"kind": "medium"}
    ks = body["knowledgeSourceParams"][0]
    assert ks["knowledgeSourceName"] == "ks" and "tenant_id eq 't1'" in ks["filterAddOn"] and "search.in(document_id" in ks["filterAddOn"]
    assert "entra_token" not in ks["filterAddOn"]
    assert a._url().startswith("https://svc.search.windows.net/knowledgebases('kb')/retrieve?api-version=")
    assert a._headers(user_token="tok")["x-ms-query-source-authorization"] == "tok"
    assert a.mcp_url.endswith("/knowledgebases/kb/mcp?api-version=2026-08-01-preview")


def test_foundry_parses_references_and_activity():
    data = {
        "response": [{"content": [{"type": "text", "text": json.dumps([{"ref_id": 0, "title": "T", "content": "ignored"}])}]}],
        "activity": [{"type": "modelQueryPlanning", "inputTokens": 100, "outputTokens": 10},
                     {"type": "searchIndex", "searchIndexArguments": {"search": "sky blue"}, "count": 3}],
        "references": [{"type": "searchIndex", "id": "0", "docKey": "doc_17", "rerankerScore": 3.2,
                        "sourceData": {"chunk": "The sky is blue because of Rayleigh scattering.", "title": "Physics", "page": 4}}],
    }
    chunks = FoundryIQAdapter.parse_response(data, "why")
    assert len(chunks) == 1 and chunks[0].content.startswith("The sky") and chunks[0].source == "Physics"
    assert chunks[0].page == 4 and chunks[0].backend == "foundry_iq" and chunks[0].rerank_score == 3.2
    assert FoundryIQAdapter.executed_queries_from_activity(data) == ["sky blue"]


def test_foundry_parses_extractive_text_when_no_references():
    data = {"response": [{"content": [{"type": "text", "text": json.dumps([{"ref_id": 1, "title": "A", "content": "alpha"}])}]}]}
    chunks = FoundryIQAdapter.parse_response(data, "q")
    assert chunks[0].content == "alpha" and chunks[0].source == "A"


@pytest.mark.asyncio
async def test_foundry_retrieve_over_mock_transport():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if "knowledgebases('kb')" in str(request.url):
            return httpx.Response(404)
        body = json.loads(request.content)
        assert body["messages"][0]["content"][0]["text"] == "q"
        return httpx.Response(200, json={"references": [{"id": "0", "docKey": "d", "rerankerScore": 2.0, "sourceData": {"chunk": "hit", "title": "Doc"}}],
                                         "activity": [{"type": "searchIndex", "searchIndexArguments": {"search": "q"}, "inputTokens": 5}]})

    a = FoundryIQAdapter(endpoint="https://svc.search.windows.net", api_key="k", knowledge_base="kb",
                         client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    r = await a.retrieve(RetrievalRequest(query="q", top_k=3))
    assert r.backend == "foundry_iq" and r.chunks[0].content == "hit"
    assert a.path_style == "plain"           # fell back after the 404
    assert r.metadata["usage"]["inputTokens"] == 5


@pytest.mark.asyncio
async def test_foundry_unconfigured_raises():
    with pytest.raises(FoundryIQError):
        await FoundryIQAdapter(endpoint="", api_key="", knowledge_base="").retrieve(RetrievalRequest(query="q"))
