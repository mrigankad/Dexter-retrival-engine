import json
from pathlib import Path

import pytest

SAMPLES = Path(__file__).parent.parent / "samples"


async def _upload(client, headers, name="policy.md"):
    with open(SAMPLES / name, "rb") as f:
        r = await client.post("/ingest", headers=headers, files={"file": (name, f, "text/markdown")})
    assert r.status_code == 202, r.text
    from src.ingestion.worker import wait_for_inline_jobs
    await wait_for_inline_jobs()
    return r.json()["document_id"]


@pytest.mark.asyncio
async def test_root_health_and_backends(client):
    assert (await client.get("/")).json()["version"] == "2.0.0"
    h = (await client.get("/health")).json()
    assert h["services"]["database"]["status"] == "healthy"
    assert h["services"]["knowledge"]["status"] == "healthy"
    assert h["services"]["redis"]["status"] == "disabled"
    b = (await client.get("/knowledge/backends")).json()
    assert {x["backend"] for x in b["backends"]} == {"local", "foundry_iq", "mcp", "mock"}
    assert (await client.get("/knowledge/backends/foundry_iq/health")).json()["status"] == "unconfigured"
    assert (await client.get("/knowledge/backends/nope/health")).status_code == 404
    assert (await client.get("/v1/health")).status_code == 200


@pytest.mark.asyncio
async def test_auth_flow(client):
    assert (await client.post("/auth/login", json={"username": "admin", "password": "wrong"})).status_code == 401
    r = await client.post("/auth/register", json={"username": "alice", "email": "alice@example.com", "password": "secret1"})
    assert r.status_code == 201 and r.json()["access_token"]
    assert (await client.post("/auth/register", json={"username": "alice", "email": "a2@example.com", "password": "secret1"})).status_code == 400
    refreshed = await client.post("/auth/refresh", json={"refresh_token": r.json()["refresh_token"]})
    assert refreshed.status_code == 200
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"})
    assert me.json()["username"] == "alice"
    assert (await client.get("/documents")).status_code == 401


@pytest.mark.asyncio
async def test_document_lifecycle(client, auth_headers):
    did = await _upload(client, auth_headers)
    docs = (await client.get("/documents", headers=auth_headers)).json()
    assert docs["total"] == 1 and docs["documents"][0]["status"] == "completed" and docs["documents"][0]["chunks_count"] >= 3
    one = (await client.get(f"/documents/{did}", headers=auth_headers)).json()
    assert one["filename"] == "policy.md" and one["metadata"]["parser"] == "text"
    chunks = (await client.get(f"/documents/{did}/chunks", headers=auth_headers)).json()["chunks"]
    assert len(chunks) >= 3 and chunks[0]["chunk_index"] == 0
    f = await client.get(f"/files/{did}", headers=auth_headers)
    assert f.status_code == 200 and b"Reimbursement" in f.content
    assert (await client.get(f"/files/{did}")).status_code == 401
    rep = await client.post(f"/documents/{did}/reprocess", headers=auth_headers)
    assert rep.status_code == 200
    from src.ingestion.worker import wait_for_inline_jobs
    await wait_for_inline_jobs()
    assert (await client.delete(f"/documents/{did}", headers=auth_headers)).json()["status"] == "deleted"
    assert (await client.get(f"/documents/{did}", headers=auth_headers)).status_code == 404
    bad = await client.post("/ingest", headers=auth_headers, files={"file": ("x.exe", b"abc", "application/octet-stream")})
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_retrieve_and_chat_json(client, auth_headers):
    await _upload(client, auth_headers)
    r = await client.post("/knowledge/retrieve", headers=auth_headers, json={"query": "hotel limit tier 1", "top_k": 2})
    assert r.status_code == 200 and len(r.json()["chunks"]) == 2
    # anonymous callers only see public documents (this one is tenant-visible)
    r = await client.post("/knowledge/retrieve", json={"query": "hotel limit tier 1", "top_k": 2})
    assert r.status_code == 200 and r.json()["chunks"] == []
    r = await client.post("/chat", headers=auth_headers, json={"query": "What is the hotel limit per night in a Tier 1 city?", "stream": False})
    j = r.json()
    assert r.status_code == 200 and j["intent"] == "KNOWLEDGE" and j["confidence"] == "high"
    assert j["sources"] and j["evidence"] and [c["marker"] for c in j["citations"]] == ["[1]", "[2]"]
    assert j["trace_id"] and (await client.get(f"/traces/{j['trace_id']}", headers=auth_headers)).json()["intent"] == "KNOWLEDGE"
    r = await client.post("/chat", headers=auth_headers, json={"query": "hotel limit", "stream": False, "backend": "mock"})
    assert r.status_code == 200 and "couldn't find" in r.json()["response"]


@pytest.mark.asyncio
async def test_chat_sse_stream_and_history(client, auth_headers):
    await _upload(client, auth_headers)
    events, data = [], {}
    async with client.stream("POST", "/chat", headers=auth_headers, json={"query": "What is the hotel limit per night in a Tier 1 city?", "session_id": "s42"}) as resp:
        assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/event-stream")
        current = None
        async for line in resp.aiter_lines():
            if line.startswith("event:"):
                current = line.split(":", 1)[1].strip()
                events.append(current)
            elif line.startswith("data:") and current in ("done", "metadata", "evidence", "sources"):
                data.setdefault(current, []).append(line[5:].strip())
    assert events[0] == "start" and "progress" in events and "evidence" in events and "answer_delta" in events
    assert events[-2:] == ["done", "metadata"]
    meta = json.loads(data["metadata"][0])
    assert meta["session_id"] == "s42" and meta["message_id"]
    assert json.loads(data["sources"][0])[0]["source"] == "policy.md"
    hist = (await client.get("/chat/history/s42", headers=auth_headers)).json()["messages"]
    assert [m["role"] for m in hist] == ["user", "assistant"] and hist[1]["metadata"]["trace_id"]
    assert (await client.get("/chat/sessions", headers=auth_headers)).json()["sessions"][0]["id"] == "s42"
    assert (await client.delete("/chat/history/s42", headers=auth_headers)).json()["status"] == "cleared"
    assert (await client.post("/chat/feedback", headers=auth_headers, json={"trace_id": meta["trace_id"], "rating": 1})).status_code == 201


@pytest.mark.asyncio
async def test_anonymous_chat_toggle(client, monkeypatch):
    from src.core.config import settings
    r = await client.post("/chat", json={"query": "hello", "stream": False})
    assert r.status_code == 200
    monkeypatch.setattr(settings, "allow_anonymous_chat", False)
    assert (await client.post("/chat", json={"query": "hello", "stream": False})).status_code == 401


@pytest.mark.asyncio
async def test_evaluation_endpoints(client, auth_headers, tmp_path):
    await _upload(client, auth_headers)
    assert (await client.get("/evaluations/not-a-uuid")).status_code == 404
    ds = tmp_path / "ds.json"
    ds.write_text(json.dumps([{"question": "hotel limit tier 1 city", "relevant": ["policy.md"], "expected_substrings": ["220"]}]))
    r = await client.post("/evaluations/run", headers=auth_headers, json={"dataset_path": str(ds), "top_k": 3})
    assert r.status_code == 200 and r.json()["hit_rate"] == 1.0
    assert (await client.post("/evaluations/run", headers=auth_headers, json={"dataset_path": "nope.json"})).status_code == 404
