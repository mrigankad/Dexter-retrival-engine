"""
SharePoint / OneDrive via Microsoft Graph, with permission sync.

Settings: tenant_id, client_id, client_secret (env:...), and one of drive_id | site_id
(site's default document library) | user_id (OneDrive); optional folder_path, scope.
Alternatively ``access_token`` (env:...) for delegated tokens in dev.

ACL: item permissions (grantedToV2 / grantedToIdentitiesV2) map to ``user:<oid>``,
``group:<id>``; sharing links with scope ``organization`` → ``tenant:<tenant>``,
``anonymous`` → ``public``. Users must therefore be identified by their Entra object id
(AUTH_MODE=entra) for per-user trimming to line up.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from .base import Connector, ConnectorError, SourceItem, ext_of, register_connector

GRAPH = "https://graph.microsoft.com/v1.0"


def map_graph_permissions(permissions: List[Dict[str, Any]], tenant_principal: Optional[str]) -> List[str]:
    out: List[str] = []
    for perm in permissions:
        identities: List[Dict[str, Any]] = []
        for key in ("grantedToV2", "grantedTo"):
            if isinstance(perm.get(key), dict):
                identities.append(perm[key])
        for key in ("grantedToIdentitiesV2", "grantedToIdentities"):
            identities.extend(i for i in perm.get(key) or [] if isinstance(i, dict))
        for ident in identities:
            user = ident.get("user") or {}
            group = ident.get("group") or ident.get("siteGroup") or {}
            if user.get("id"):
                out.append(f"user:{user['id']}")
            elif user.get("email"):
                out.append(f"user:{user['email'].lower()}")
            if group.get("id"):
                out.append(f"group:{group['id']}")
        link = perm.get("link") or {}
        scope = (link.get("scope") or "").lower()
        if scope == "anonymous":
            out.append("public")
        elif scope == "organization" and tenant_principal:
            out.append(tenant_principal)
    return sorted(set(out))


@register_connector
class MicrosoftGraphConnector(Connector):
    type = "sharepoint"
    description = "SharePoint document library or OneDrive via Microsoft Graph (permission sync)"
    required_settings = []

    def __init__(self, config, client: Optional[httpx.AsyncClient] = None):
        super().__init__(config)
        s = config.settings
        if not (s.get("drive_id") or s.get("site_id") or s.get("user_id")):
            raise ConnectorError("sharepoint connector needs drive_id, site_id or user_id")
        if not s.get("access_token") and not (s.get("tenant_id") and s.get("client_id") and s.get("client_secret")):
            raise ConnectorError("sharepoint connector needs access_token or tenant_id + client_id + client_secret")
        self._client = client
        self._token: Optional[str] = None
        self._token_exp = 0.0
        self._drive_id: Optional[str] = s.get("drive_id")
        self._next_cursor: Optional[str] = None
        self.graph = s.get("graph_url", GRAPH).rstrip("/")

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def _get_token(self) -> str:
        static = self.config.secret("access_token")
        if static:
            return static
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        s = self.config.settings
        authority = s.get("authority", "https://login.microsoftonline.com")
        r = await self._http().post(
            f"{authority}/{s['tenant_id']}/oauth2/v2.0/token",
            data={"client_id": s["client_id"], "client_secret": self.config.secret("client_secret"),
                  "scope": s.get("scope", "https://graph.microsoft.com/.default"), "grant_type": "client_credentials"},
        )
        if r.status_code >= 400:
            raise ConnectorError(f"Token request failed {r.status_code}: {r.text[:200]}")
        data = r.json()
        self._token, self._token_exp = data["access_token"], time.time() + int(data.get("expires_in", 3600))
        return self._token

    async def _get(self, url: str, **params) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {await self._get_token()}"}
        r = await self._http().get(url if url.startswith("http") else f"{self.graph}{url}", headers=headers, params=params or None)
        if r.status_code >= 400:
            raise ConnectorError(f"Graph {url} failed {r.status_code}: {r.text[:200]}")
        return r.json()

    async def _drive(self) -> str:
        if self._drive_id:
            return self._drive_id
        s = self.config.settings
        if s.get("site_id"):
            data = await self._get(f"/sites/{s['site_id']}/drive")
        else:
            data = await self._get(f"/users/{s['user_id']}/drive")
        self._drive_id = data["id"]
        return self._drive_id

    async def test_connection(self) -> Dict[str, Any]:
        drive = await self._drive()
        data = await self._get(f"/drives/{drive}")
        return {"status": "ok", "drive_id": drive, "drive_name": data.get("name"), "drive_type": data.get("driveType")}

    async def list_items(self) -> AsyncIterator[SourceItem]:
        drive = await self._drive()
        folder = (self.config.settings.get("folder_path") or "").strip("/")
        url = self.config.delta_cursor or (f"/drives/{drive}/root:/{folder}:/delta" if folder else f"/drives/{drive}/root/delta")
        tenant_principal = f"tenant:{self.config.tenant_id}" if self.config.tenant_id else None
        while url:
            data = await self._get(url)
            for item in data.get("value", []):
                if item.get("deleted"):
                    yield SourceItem(external_id=item["id"], title=item.get("name", ""), file_type="", metadata={"deleted": True})
                    continue
                if "file" not in item:
                    continue
                ext = ext_of(item.get("name", ""), (item.get("file") or {}).get("mimeType"))
                principals: List[str] = []
                if self.config.inherit_source_acl:
                    try:
                        perms = await self._get(f"/drives/{drive}/items/{item['id']}/permissions")
                        principals = map_graph_permissions(perms.get("value", []), tenant_principal)
                    except ConnectorError:
                        principals = []
                yield SourceItem(
                    external_id=item["id"], title=item.get("name", item["id"]), file_type=ext,
                    url=item.get("webUrl"), size=item.get("size"), etag=item.get("eTag") or item.get("cTag"),
                    modified=datetime.fromisoformat(item["lastModifiedDateTime"].replace("Z", "+00:00")) if item.get("lastModifiedDateTime") else None,
                    principals=principals,
                    metadata={"download_url": item.get("@microsoft.graph.downloadUrl"),
                              "parent": (item.get("parentReference") or {}).get("path")},
                )
            url = data.get("@odata.nextLink")
            if data.get("@odata.deltaLink"):
                self._next_cursor = data["@odata.deltaLink"]

    def new_cursor(self) -> Optional[str]:
        return self._next_cursor

    async def fetch(self, item: SourceItem) -> bytes:
        download = item.metadata.get("download_url")
        if download:
            r = await self._http().get(download)
        else:
            drive = await self._drive()
            r = await self._http().get(f"{self.graph}/drives/{drive}/items/{item.external_id}/content",
                                       headers={"Authorization": f"Bearer {await self._get_token()}"}, follow_redirects=True)
        if r.status_code >= 400:
            raise ConnectorError(f"Download failed {r.status_code}")
        return r.content

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
