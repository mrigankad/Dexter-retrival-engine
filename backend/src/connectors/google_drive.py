"""
Google Drive folder via the Drive v3 REST API, with permission sync.

Settings: folder_id (or 'root'), access_token (env:...) – an OAuth access token with
drive.readonly scope (service-account/refresh flows can be added around this); optional
include_subfolders (default true), domain (maps domain-wide shares to the tenant).

ACL: permission type user → user:<email>, group → group:<email>, domain → tenant:<tenant>,
anyone → public.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from .base import Connector, ConnectorError, SourceItem, ext_of, register_connector

DRIVE = "https://www.googleapis.com/drive/v3"
EXPORTS = {
    "application/vnd.google-apps.document": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"),
    "application/vnd.google-apps.spreadsheet": ("text/csv", "csv"),
    "application/vnd.google-apps.presentation": ("text/plain", "txt"),
}
FIELDS = "nextPageToken,files(id,name,mimeType,modifiedTime,md5Checksum,size,webViewLink,permissions(type,emailAddress,domain,role))"


def map_drive_permissions(permissions: List[Dict[str, Any]], tenant_principal: Optional[str]) -> List[str]:
    out: List[str] = []
    for p in permissions or []:
        t = p.get("type")
        if t == "user" and p.get("emailAddress"):
            out.append(f"user:{p['emailAddress'].lower()}")
        elif t == "group" and p.get("emailAddress"):
            out.append(f"group:{p['emailAddress'].lower()}")
        elif t == "domain" and tenant_principal:
            out.append(tenant_principal)
        elif t == "anyone":
            out.append("public")
    return sorted(set(out))


@register_connector
class GoogleDriveConnector(Connector):
    type = "google_drive"
    description = "Google Drive folder (permission sync)"
    required_settings = ["folder_id", "access_token"]

    def __init__(self, config, client: Optional[httpx.AsyncClient] = None):
        super().__init__(config)
        self._client = client
        self.api = config.settings.get("api_url", DRIVE).rstrip("/")

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.config.secret('access_token')}"}

    async def _get(self, path: str, **params) -> httpx.Response:
        r = await self._http().get(f"{self.api}{path}", headers=self._headers(), params=params)
        if r.status_code >= 400:
            raise ConnectorError(f"Drive {path} failed {r.status_code}: {r.text[:200]}")
        return r

    async def test_connection(self) -> Dict[str, Any]:
        r = await self._get(f"/files/{self.config.settings['folder_id']}", fields="id,name,mimeType")
        return {"status": "ok", "folder": r.json().get("name")}

    async def _walk(self, folder_id: str) -> AsyncIterator[Dict[str, Any]]:
        token = None
        while True:
            params = {"q": f"'{folder_id}' in parents and trashed = false", "fields": FIELDS, "pageSize": 200, "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
            if token:
                params["pageToken"] = token
            data = (await self._get("/files", **params)).json()
            for f in data.get("files", []):
                if f.get("mimeType") == "application/vnd.google-apps.folder":
                    if self.config.settings.get("include_subfolders", True):
                        async for sub in self._walk(f["id"]):
                            yield sub
                else:
                    yield f
            token = data.get("nextPageToken")
            if not token:
                break

    async def list_items(self) -> AsyncIterator[SourceItem]:
        tenant_principal = f"tenant:{self.config.tenant_id}" if self.config.tenant_id else None
        async for f in self._walk(self.config.settings["folder_id"]):
            mime = f.get("mimeType", "")
            if mime in EXPORTS:
                ext = EXPORTS[mime][1]
            else:
                ext = ext_of(f.get("name", ""), mime)
            yield SourceItem(
                external_id=f["id"], title=f.get("name", f["id"]), file_type=ext, url=f.get("webViewLink"),
                modified=datetime.fromisoformat(f["modifiedTime"].replace("Z", "+00:00")) if f.get("modifiedTime") else None,
                size=int(f["size"]) if f.get("size") else None, etag=f.get("md5Checksum") or f.get("modifiedTime"),
                principals=map_drive_permissions(f.get("permissions"), tenant_principal) if self.config.inherit_source_acl else [],
                metadata={"mime_type": mime},
            )

    async def fetch(self, item: SourceItem) -> bytes:
        mime = item.metadata.get("mime_type", "")
        if mime in EXPORTS:
            r = await self._get(f"/files/{item.external_id}/export", mimeType=EXPORTS[mime][0])
        else:
            r = await self._get(f"/files/{item.external_id}", alt="media", supportsAllDrives="true")
        return r.content

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
