import json
import os
from pathlib import Path

import httpx
import pytest

from src.connectors import ConnectorConfig, ConnectorSyncService
from src.connectors.sync import config_from_row

SAMPLES = Path(__file__).parent.parent / "samples"


async def _wait():
    from src.ingestion.worker import wait_for_inline_jobs
    await wait_for_inline_jobs()


async def _create_connector(client, headers, **body):
    r = await client.post("/connectors", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_local_folder_sync_lifecycle(client, auth_headers, tmp_path):
    src = tmp_path / "docs"
    src.mkdir()
    (src / "policy.md").write_bytes((SAMPLES / "policy.md").read_bytes())
    (src / "handbook.md").write_bytes((SAMPLES / "handbook.md").read_bytes())
    (src / "ignored.exe").write_bytes(b"binary")

    assert (await client.get("/connectors/types", headers=auth_headers)).status_code == 200
    cid = await _create_connector(client, auth_headers, type="local_folder", name="shared drive",
                                  settings={"path": str(src)}, visibility="tenant", shared_groups=["legal"])
    assert (await client.post(f"/connectors/{cid}/test", headers=auth_headers)).json()["files"] == 3

    report = (await client.post(f"/connectors/{cid}/sync", headers=auth_headers)).json()
    await _wait()
    assert report["status"] == "completed" and report["added"] == 2 and report["skipped"] == 1 and report["removed"] == 0

    docs = (await client.get("/documents", headers=auth_headers)).json()["documents"]
    assert {d["filename"] for d in docs} == {"policy.md", "handbook.md"}
    assert all(d["status"] == "completed" and d["metadata"]["connector"] == "shared drive" for d in docs)
    assert all(d["visibility"] == "tenant" and d["shared_groups"] == ["legal"] for d in docs)
    r = await client.post("/knowledge/retrieve", headers=auth_headers, json={"query": "hotel limit per night tier 1", "top_k": 2})
    assert r.json()["chunks"][0]["source"] == "policy.md"
    assert r.json()["chunks"][0]["metadata"]["url"].startswith("file://")

    # unchanged run → everything skipped
    report = (await client.post(f"/connectors/{cid}/sync", headers=auth_headers)).json()
    assert report["added"] == 0 and report["updated"] == 0 and report["skipped"] == 3

    # modify one file, delete another
    (src / "policy.md").write_text((SAMPLES / "policy.md").read_text() + "\n\n## 5. Addendum\nPer diem for Mars trips is 999 USD.\n")
    os.utime(src / "policy.md", None)
    (src / "handbook.md").unlink()
    report = (await client.post(f"/connectors/{cid}/sync", headers=auth_headers)).json()
    await _wait()
    assert report["updated"] == 1 and report["removed"] == 1
    docs = (await client.get("/documents", headers=auth_headers)).json()["documents"]
    assert {d["filename"] for d in docs} == {"policy.md"}
    r = await client.post("/knowledge/retrieve", headers=auth_headers, json={"query": "per diem Mars trips", "top_k": 2})
    assert any("999" in c["content"] for c in r.json()["chunks"])

    runs = (await client.get(f"/connectors/{cid}/runs", headers=auth_headers)).json()["runs"]
    assert len(runs) == 3 and runs[0]["status"] == "completed"
    items = (await client.get(f"/connectors/{cid}/items", headers=auth_headers)).json()["items"]
    assert len(items) == 1 and "tenant:default" in items[0]["principals"] and "group:legal" in items[0]["principals"]
    listed = (await client.get("/connectors", headers=auth_headers)).json()["connectors"]
    assert listed[0]["items"] == 1 and listed[0]["last_status"] == "completed"

    # non-admins cannot manage connectors
    r = await client.post("/auth/register", json={"username": "eve", "email": "eve@example.com", "password": "secret1"})
    eve = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.get("/connectors", headers=eve)).status_code == 403

    r = await client.delete(f"/connectors/{cid}", headers=auth_headers)
    assert r.status_code == 200 and r.json()["documents_removed"] == 1
    assert (await client.get("/documents", headers=auth_headers)).json()["total"] == 0


@pytest.mark.asyncio
async def test_create_connector_validates_settings(client, auth_headers):
    r = await client.post("/connectors", headers=auth_headers, json={"type": "sharepoint", "name": "sp", "settings": {}})
    assert r.status_code == 400 and "drive_id" in r.json()["detail"]
    r = await client.post("/connectors", headers=auth_headers, json={"type": "nope", "name": "x", "settings": {}})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_web_connector_sync_with_mock_transport(client, auth_headers):
    pages = {
        "https://example.test/sitemap.xml": ("application/xml", b"<urlset><url><loc>https://example.test/policy</loc></url></urlset>"),
        "https://example.test/policy": ("text/html", b"<html><head><title>Travel Policy</title></head><body><h1>Travel Policy</h1><p>Hotel stays are capped at 220 USD per night in Tier 1 cities.</p></body></html>"),
        "https://example.test/faq": ("text/html", b"<html><head><title>FAQ</title></head><body><p>Claims must be submitted within 30 days.</p></body></html>"),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url in pages:
            ct, body = pages[url]
            return httpx.Response(200, headers={"content-type": ct}, content=body if request.method == "GET" else b"")
        return httpx.Response(404)

    from src.connectors.web import WebConnector
    cid = await _create_connector(client, auth_headers, type="web", name="site", visibility="public",
                                  settings={"urls": ["https://example.test/faq"], "sitemap_url": "https://example.test/sitemap.xml"})
    async with __import__("src.infrastructure.database", fromlist=["session_scope"]).session_scope() as db:
        from src.infrastructure.database import ConnectorRow
        config = config_from_row(await db.get(ConnectorRow, cid))
    connector = WebConnector(config, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    report = await ConnectorSyncService().sync(cid, connector=connector)
    await _wait()
    assert report.added == 2 and report.status == "completed", report
    docs = (await client.get("/documents", headers=auth_headers)).json()["documents"]
    assert {d["filename"] for d in docs} == {"Travel Policy.html", "FAQ.html"}
    # public visibility → anonymous retrieval works and cites the URL
    r = await client.post("/knowledge/retrieve", json={"query": "hotel cap tier 1 cities", "top_k": 1})
    chunk = r.json()["chunks"][0]
    assert chunk["source"] == "Travel Policy.html" and chunk["metadata"]["url"] == "https://example.test/policy"


@pytest.mark.asyncio
async def test_sharepoint_connector_lists_permissions_and_cursor(client, auth_headers):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if url.endswith("/oauth2/v2.0/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        if url.endswith("/drives/drive-1"):
            return httpx.Response(200, json={"id": "drive-1", "name": "Documents", "driveType": "documentLibrary"})
        if "/root/delta" in url and "page2" not in url:
            return httpx.Response(200, json={"value": [
                {"id": "item-1", "name": "policy.md", "file": {"mimeType": "text/markdown"}, "size": 10, "eTag": "e1",
                 "lastModifiedDateTime": "2026-10-01T10:00:00Z", "webUrl": "https://contoso.sharepoint.com/policy.md",
                 "@microsoft.graph.downloadUrl": "https://download.test/item-1"},
                {"id": "folder-1", "name": "Sub", "folder": {}},
            ], "@odata.nextLink": "https://graph.microsoft.com/v1.0/drives/drive-1/root/delta?page2"})
        if "page2" in url:
            return httpx.Response(200, json={"value": [{"id": "item-2", "name": "old.md", "deleted": {"state": "deleted"}}],
                                             "@odata.deltaLink": "https://graph.microsoft.com/v1.0/drives/drive-1/root/delta?token=abc"})
        if url.endswith("/items/item-1/permissions"):
            return httpx.Response(200, json={"value": [{"grantedToV2": {"user": {"id": "oid-7"}}}, {"link": {"scope": "organization"}}]})
        if url == "https://download.test/item-1":
            return httpx.Response(200, content=(SAMPLES / "policy.md").read_bytes())
        return httpx.Response(404, text=url)

    from src.connectors.microsoft_graph import MicrosoftGraphConnector
    cid = await _create_connector(client, auth_headers, type="sharepoint", name="sp", visibility="source", tenant_id="t1",
                                  settings={"tenant_id": "tid", "client_id": "cid", "client_secret": "env:SP_SECRET", "drive_id": "drive-1"})
    from src.infrastructure.database import ConnectorRow, session_scope
    async with session_scope() as db:
        config = config_from_row(await db.get(ConnectorRow, cid))
    connector = MicrosoftGraphConnector(config, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert (await connector.test_connection())["drive_name"] == "Documents"
    report = await ConnectorSyncService().sync(cid, connector=connector)
    await _wait()
    assert report.added == 1 and report.removed == 0 and report.status == "completed", report
    items = (await client.get(f"/connectors/{cid}/items", headers=auth_headers)).json()["items"]
    assert items[0]["principals"] == ["tenant:t1", "user:oid-7"]
    async with session_scope() as db:
        row = await db.get(ConnectorRow, cid)
        assert row.delta_cursor.endswith("token=abc") and row.last_status == "completed"
    # only a member of the source ACL can retrieve it
    assert (await client.post("/knowledge/retrieve", json={"query": "hotel limit", "top_k": 1})).json()["chunks"] == []
    from src.core.security import create_token_pair
    member = {"Authorization": f"Bearer {create_token_pair('oid-7', 'member', tenant_id='t1').access_token}"}
    r = await client.post("/knowledge/retrieve", headers=member, json={"query": "hotel limit per night", "top_k": 1})
    assert r.json()["chunks"] and r.json()["chunks"][0]["source"] == "policy.md"


@pytest.mark.asyncio
async def test_google_drive_and_confluence_listing():
    from src.connectors.confluence import ConfluenceConnector
    from src.connectors.google_drive import GoogleDriveConnector

    def drive_handler(request: httpx.Request) -> httpx.Response:
        url = request.url.path
        if url.endswith("/files"):
            q = request.url.params.get("q", "")
            if "'root-1'" in q:
                return httpx.Response(200, json={"files": [
                    {"id": "sub", "name": "Sub", "mimeType": "application/vnd.google-apps.folder"},
                    {"id": "doc-1", "name": "Policy", "mimeType": "application/vnd.google-apps.document", "modifiedTime": "2026-10-01T10:00:00Z",
                     "webViewLink": "https://docs.google.com/doc-1", "permissions": [{"type": "user", "emailAddress": "a@x.com"}, {"type": "anyone"}]}]})
            return httpx.Response(200, json={"files": [{"id": "pdf-1", "name": "report.pdf", "mimeType": "application/pdf", "size": "12", "md5Checksum": "m1"}]})
        if url.endswith("/files/doc-1/export"):
            return httpx.Response(200, content=b"exported")
        if url.endswith("/files/pdf-1"):
            return httpx.Response(200, content=b"%PDF")
        return httpx.Response(404, text=url)

    cfg = ConnectorConfig(type="google_drive", name="gd", tenant_id="t1", settings={"folder_id": "root-1", "access_token": "tok"})
    gd = GoogleDriveConnector(cfg, client=httpx.AsyncClient(transport=httpx.MockTransport(drive_handler)))
    items = [i async for i in gd.list_items()]
    assert {i.title for i in items} == {"Policy", "report.pdf"}
    doc = next(i for i in items if i.external_id == "doc-1")
    assert doc.file_type == "docx" and doc.principals == ["public", "user:a@x.com"] and await gd.fetch(doc) == b"exported"
    pdf = next(i for i in items if i.external_id == "pdf-1")
    assert pdf.file_type == "pdf" and pdf.etag == "m1" and await gd.fetch(pdf) == b"%PDF"

    def conf_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/api/v2/spaces?" in url or url.endswith("/api/v2/spaces"):
            return httpx.Response(200, json={"results": [{"id": "123", "key": "ENG"}]})
        if url.rstrip("/").endswith("/api/v2/spaces/123/pages") or "/spaces/123/pages?" in url:
            return httpx.Response(200, json={"results": [{"id": "p1", "title": "Runbook", "version": {"number": 3, "createdAt": "2026-10-01T10:00:00Z"},
                                                           "body": {"storage": {"value": "<p>Restart the service.</p>"}}, "_links": {"webui": "/spaces/ENG/pages/p1"}}],
                                             "_links": {}})
        if url.endswith("/rest/api/content/p1/restriction/byOperation"):
            return httpx.Response(200, json={"read": {"restrictions": {"user": {"results": [{"accountId": "acc-1"}]}}}})
        return httpx.Response(404, text=url)

    cfg = ConnectorConfig(type="confluence", name="cf", settings={"base_url": "https://x.atlassian.net/wiki", "email": "e", "api_token": "t", "space_key": "ENG"})
    cf = ConfluenceConnector(cfg, client=httpx.AsyncClient(transport=httpx.MockTransport(conf_handler)))
    assert (await cf.test_connection())["space_id"] == "123"
    pages = [i async for i in cf.list_items()]
    assert pages[0].title == "Runbook.html" and pages[0].principals == ["user:acc-1"] and pages[0].etag == "3"
    assert b"Restart the service" in await cf.fetch(pages[0])


@pytest.mark.asyncio
async def test_s3_connector_with_fake_client():
    from src.connectors.s3 import S3Connector

    class FakeS3:
        def list_objects_v2(self, **kw):
            if kw.get("ContinuationToken"):
                return {"Contents": [{"Key": "docs/b.txt", "Size": 2, "ETag": '"e2"'}], "IsTruncated": False}
            return {"Contents": [{"Key": "docs/a.pdf", "Size": 1, "ETag": '"e1"'}, {"Key": "docs/", "Size": 0}],
                    "IsTruncated": True, "NextContinuationToken": "n"}

        def get_object(self, **kw):
            import io
            return {"Body": io.BytesIO(b"data-" + kw["Key"].encode())}

    cfg = ConnectorConfig(type="s3", name="s3", settings={"bucket": "b", "prefix": "docs/"})
    s3 = S3Connector(cfg, client=FakeS3())
    assert (await s3.test_connection())["status"] == "ok"
    items = [i async for i in s3.list_items()]
    assert [i.external_id for i in items] == ["docs/a.pdf", "docs/b.txt"] and items[0].etag == "e1"
    assert await s3.fetch(items[1]) == b"data-docs/b.txt"


@pytest.mark.asyncio
async def test_scheduler_runs_due_connectors(client, auth_headers, tmp_path):
    from src.connectors.scheduler import run_due_syncs
    src = tmp_path / "d"
    src.mkdir()
    (src / "handbook.md").write_bytes((SAMPLES / "handbook.md").read_bytes())
    cid = await _create_connector(client, auth_headers, type="local_folder", name="sched", settings={"path": str(src)}, schedule_minutes=1)
    assert await run_due_syncs() == 1
    await _wait()
    assert await run_due_syncs() == 0            # just ran, not due again
    runs = (await client.get(f"/connectors/{cid}/runs", headers=auth_headers)).json()["runs"]
    assert len(runs) == 1 and runs[0]["added"] == 1
