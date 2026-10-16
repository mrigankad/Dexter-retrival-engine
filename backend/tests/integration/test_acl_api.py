"""Permission model through the HTTP API: visibility, groups, admin, anonymous."""

from pathlib import Path

import pytest

SAMPLES = Path(__file__).parent.parent / "samples"


async def _register(client, name):
    r = await client.post("/auth/register", json={"username": name, "email": f"{name}@example.com", "password": "secret1"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _login(client, name, password="secret1"):
    r = await client.post("/auth/login", json={"username": name, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _upload(client, headers, name, visibility=None, groups=None):
    data = {}
    if visibility:
        data["visibility"] = visibility
    if groups:
        data["groups"] = groups
    with open(SAMPLES / name, "rb") as f:
        r = await client.post("/ingest", headers=headers, data=data, files={"file": (name, f, "text/markdown")})
    assert r.status_code == 202, r.text
    from src.ingestion.worker import wait_for_inline_jobs
    await wait_for_inline_jobs()
    return r.json()["document_id"]


async def _retrieve_sources(client, headers, query):
    r = await client.post("/knowledge/retrieve", headers=headers or {}, json={"query": query, "top_k": 5})
    assert r.status_code == 200, r.text
    return {c["source"] for c in r.json()["chunks"]}


@pytest.mark.asyncio
async def test_private_tenant_public_visibility(client, auth_headers):
    alice = await _register(client, "alice")
    bob = await _register(client, "bob")
    private_id = await _upload(client, alice, "policy.md", visibility="private")
    await _upload(client, alice, "handbook.md", visibility="tenant")

    # Alice sees both; Bob (same default tenant) sees only the tenant-shared one
    assert {d["filename"] for d in (await client.get("/documents", headers=alice)).json()["documents"]} == {"policy.md", "handbook.md"}
    assert {d["filename"] for d in (await client.get("/documents", headers=bob)).json()["documents"]} == {"handbook.md"}
    assert (await client.get(f"/documents/{private_id}", headers=bob)).status_code == 404
    assert (await client.delete(f"/documents/{private_id}", headers=bob)).status_code == 404

    # retrieval honours the same ACL, derived from the token
    assert "policy.md" in await _retrieve_sources(client, alice, "hotel limit per night tier 1")
    assert "policy.md" not in await _retrieve_sources(client, bob, "hotel limit per night tier 1")
    assert "handbook.md" in await _retrieve_sources(client, bob, "annual leave days")
    # anonymous callers see nothing that is not public
    assert await _retrieve_sources(client, None, "hotel limit annual leave") == set()
    # admin sees everything in the tenant
    assert "policy.md" in await _retrieve_sources(client, auth_headers, "hotel limit per night tier 1")

    # chat for Bob cannot leak Alice's private document
    r = await client.post("/chat", headers=bob, json={"query": "What is the hotel limit per night in a Tier 1 city?", "stream": False})
    assert r.status_code == 200 and all(s["source"] != "policy.md" for s in r.json()["sources"])


@pytest.mark.asyncio
async def test_group_sharing_and_admin_user_management(client, auth_headers):
    alice = await _register(client, "alice")
    carol = await _register(client, "carol")
    doc_id = await _upload(client, alice, "policy.md", visibility="private", groups="finance")
    assert "policy.md" not in await _retrieve_sources(client, carol, "hotel limit per night")

    # admin puts Carol in the finance group; she re-logs to get the claim
    r = await client.put("/auth/users/carol", headers=auth_headers, json={"groups": ["finance"]})
    assert r.status_code == 200 and r.json()["groups"] == ["finance"]
    assert (await client.put("/auth/users/carol", headers=carol, json={"role": "admin"})).status_code == 403
    carol = await _login(client, "carol")
    assert (await client.get("/auth/me", headers=carol)).json()["groups"] == ["finance"]
    assert "policy.md" in await _retrieve_sources(client, carol, "hotel limit per night")
    assert {d["filename"] for d in (await client.get("/documents", headers=carol)).json()["documents"]} == {"policy.md"}
    # Carol can read but not delete or re-share Alice's document
    assert (await client.delete(f"/documents/{doc_id}", headers=carol)).status_code == 403
    assert (await client.put(f"/documents/{doc_id}/sharing", headers=carol, json={"visibility": "public"})).status_code == 403

    # Alice makes it public: anonymous retrieval now sees it (after re-index)
    r = await client.put(f"/documents/{doc_id}/sharing", headers=alice, json={"visibility": "public", "groups": []})
    assert r.status_code == 200 and r.json()["visibility"] == "public" and r.json()["shared_groups"] == []
    from src.ingestion.worker import wait_for_inline_jobs
    await wait_for_inline_jobs()
    assert "policy.md" in await _retrieve_sources(client, None, "hotel limit per night")
    users = (await client.get("/auth/users", headers=auth_headers)).json()
    assert {u["username"] for u in users} >= {"admin", "alice", "carol"}


@pytest.mark.asyncio
async def test_acl_can_be_disabled(client, auth_headers, monkeypatch):
    from src.core.config import settings
    alice = await _register(client, "alice")
    await _upload(client, alice, "policy.md", visibility="private")
    bob = await _register(client, "bob")
    monkeypatch.setattr(settings, "acl_enforcement", False)
    assert "policy.md" in await _retrieve_sources(client, bob, "hotel limit per night tier 1")
