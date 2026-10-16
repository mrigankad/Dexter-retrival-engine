"""
Confluence Cloud space via the REST API (v2 pages + v1 restrictions).

Settings: base_url (https://<site>.atlassian.net/wiki), email, api_token (env:...), space_key.
Pages are stored as HTML (body.storage). Read restrictions on a page map to
user:<accountId> / group:<groupId>; unrestricted pages use the connector's visibility.
"""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from .base import Connector, ConnectorError, SourceItem, register_connector


def map_confluence_restrictions(data: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    read = (data.get("read") or {}).get("restrictions") or {}
    for u in (read.get("user") or {}).get("results", []):
        if u.get("accountId"):
            out.append(f"user:{u['accountId']}")
    for g in (read.get("group") or {}).get("results", []):
        if g.get("id") or g.get("name"):
            out.append(f"group:{g.get('id') or g.get('name')}")
    return sorted(set(out))


@register_connector
class ConfluenceConnector(Connector):
    type = "confluence"
    description = "Confluence Cloud space (page restrictions → ACL)"
    required_settings = ["base_url", "email", "api_token", "space_key"]

    def __init__(self, config, client: Optional[httpx.AsyncClient] = None):
        super().__init__(config)
        self._client = client
        self.base = config.settings["base_url"].rstrip("/")
        self._space_id: Optional[str] = None
        self._bodies: Dict[str, bytes] = {}

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    def _headers(self) -> Dict[str, str]:
        creds = base64.b64encode(f"{self.config.settings['email']}:{self.config.secret('api_token')}".encode()).decode()
        return {"Authorization": f"Basic {creds}", "Accept": "application/json"}

    async def _get(self, path: str, **params) -> Dict[str, Any]:
        r = await self._http().get(path if path.startswith("http") else f"{self.base}{path}", headers=self._headers(), params=params or None)
        if r.status_code >= 400:
            raise ConnectorError(f"Confluence {path} failed {r.status_code}: {r.text[:200]}")
        return r.json()

    async def _space(self) -> str:
        if self._space_id is None:
            data = await self._get("/api/v2/spaces", keys=self.config.settings["space_key"])
            results = data.get("results") or []
            if not results:
                raise ConnectorError(f"Space {self.config.settings['space_key']} not found")
            self._space_id = str(results[0]["id"])
        return self._space_id

    async def test_connection(self) -> Dict[str, Any]:
        return {"status": "ok", "space_id": await self._space()}

    async def list_items(self) -> AsyncIterator[SourceItem]:
        space = await self._space()
        url: Optional[str] = f"/api/v2/spaces/{space}/pages"
        params: Dict[str, Any] = {"body-format": "storage", "limit": 50}
        while url:
            data = await self._get(url, **params)
            for page in data.get("results", []):
                html = ((page.get("body") or {}).get("storage") or {}).get("value", "")
                principals: List[str] = []
                if self.config.inherit_source_acl:
                    try:
                        principals = map_confluence_restrictions(await self._get(f"/rest/api/content/{page['id']}/restriction/byOperation"))
                    except ConnectorError:
                        principals = []
                body = f"<html><head><title>{page.get('title', '')}</title></head><body>{html}</body></html>".encode()
                self._bodies[str(page["id"])] = body
                version = (page.get("version") or {})
                yield SourceItem(
                    external_id=str(page["id"]), title=f"{page.get('title', page['id'])}.html", file_type="html",
                    url=f"{self.base}{(page.get('_links') or {}).get('webui', '')}" if page.get("_links") else None,
                    modified=datetime.fromisoformat(version["createdAt"].replace("Z", "+00:00")) if version.get("createdAt") else None,
                    size=len(body), etag=str(version.get("number", "")), principals=principals,
                    metadata={"space": self.config.settings["space_key"]},
                )
            nxt = (data.get("_links") or {}).get("next")
            url = f"{self.base}{nxt}" if nxt and nxt.startswith("/") else nxt
            params = {}

    async def fetch(self, item: SourceItem) -> bytes:
        if item.external_id in self._bodies:
            return self._bodies.pop(item.external_id)
        page = await self._get(f"/api/v2/pages/{item.external_id}", **{"body-format": "storage"})
        html = ((page.get("body") or {}).get("storage") or {}).get("value", "")
        return f"<html><head><title>{page.get('title', '')}</title></head><body>{html}</body></html>".encode()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
