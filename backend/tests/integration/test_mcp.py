"""MCP server tools (in-process), the HTTP mount, and the MCP client adapter."""

import pytest


@pytest.mark.asyncio
async def test_mcp_tools_in_process(indexed_policy, services):
    from mcp.client.client import Client
    from src.mcp_server.server import build_mcp_server

    server = build_mcp_server()
    async with Client(server) as client:
        tools = await client.list_tools()
        assert {t.name for t in tools.tools} == {"knowledge_retrieve", "list_documents", "list_backends"}
        result = await client.call_tool("knowledge_retrieve", {"query": "hotel limit per night in a Tier 1 city", "top_k": 3})
        assert not result.is_error
        payload = result.structured_content
        assert payload["backend"] == "local" and len(payload["evidence"]) == 3
        assert any("220" in e["content"] for e in payload["evidence"])
        assert payload["context"].startswith("[1] policy.md")
        # anonymous in-process caller: tenant-visible documents are hidden, public ones listed
        assert (await client.call_tool("list_documents", {})).structured_content["documents"] == []
        import uuid
        from src.infrastructure.database import Document, session_scope
        async with session_scope() as db:
            (await db.get(Document, uuid.UUID(indexed_policy))).visibility = "public"
        docs = (await client.call_tool("list_documents", {})).structured_content["documents"]
        assert docs and docs[0]["filename"] == "policy.md"
        backends = (await client.call_tool("list_backends", {})).structured_content
        assert backends["default"] == "local"


@pytest.mark.asyncio
async def test_mcp_adapter_over_in_process_server(indexed_policy, services):
    from src.contracts import RetrievalRequest
    from src.knowledge import McpKnowledgeAdapter
    from src.mcp_server.server import build_mcp_server
    from src.orchestrator import RetrievalEngine

    adapter = McpKnowledgeAdapter(server=build_mcp_server(), tool_name="knowledge_retrieve", auth_token="")
    health = await adapter.healthcheck()
    assert health["status"] == "healthy" and "knowledge_retrieve" in health["tools"]
    result = await adapter.retrieve(RetrievalRequest(query="hotel limit tier 1", top_k=2))
    assert result.backend == "mcp" and len(result.chunks) == 2 and result.metadata["remote_backend"] == "local"
    assert result.context.startswith("[1] policy.md")
    # the whole engine can run on top of a remote MCP knowledge source
    fake_llm, _, _ = services
    engine = RetrievalEngine(llm=fake_llm, adapter=adapter)
    answer = await engine.answer("What is the hotel limit per night in a Tier 1 city?")
    assert answer.evidence and answer.evidence[0].backend == "mcp" and answer.citations


@pytest.mark.asyncio
async def test_mcp_http_mount(client, auth_headers, indexed_policy):
    """Drive the mounted /mcp endpoint through the real streamable-HTTP client over ASGI."""
    import httpx2
    from mcp.client.client import Client
    from mcp.client.streamable_http import streamable_http_client
    from main import app

    http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test",
                              headers={"Authorization": "Bearer test-service-token"})
    async with Client(streamable_http_client("http://test/mcp/", http_client=http)) as mcp_client:
        tools = await mcp_client.list_tools()
        assert "knowledge_retrieve" in {t.name for t in tools.tools}
        result = await mcp_client.call_tool("knowledge_retrieve", {"query": "hotel limit", "top_k": 2})
        assert not result.is_error and len(result.structured_content["evidence"]) == 2


@pytest.mark.asyncio
async def test_mcp_http_mount_rejects_bad_token(client, indexed_policy, monkeypatch):
    import httpx2
    from mcp.client.client import Client
    from mcp.client.streamable_http import streamable_http_client
    from main import app
    from src.core.config import settings

    monkeypatch.setattr(settings, "mcp_require_auth", True)
    http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test",
                              headers={"Authorization": "Bearer wrong"})
    async with Client(streamable_http_client("http://test/mcp/", http_client=http)) as mcp_client:
        result = await mcp_client.call_tool("knowledge_retrieve", {"query": "hotel limit"})
        assert result.is_error
        assert "token" in (result.content[0].text if result.content else "").lower()
