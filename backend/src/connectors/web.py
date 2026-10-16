"""Web pages. Settings: urls (list) and/or sitemap_url; optional headers, max_pages."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from .base import Connector, ConnectorError, SourceItem, ext_of, register_connector

_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


@register_connector
class WebConnector(Connector):
    type = "web"
    description = "A list of URLs and/or a sitemap"
    required_settings = []

    def __init__(self, config, client: Optional[httpx.AsyncClient] = None):
        super().__init__(config)
        if not config.settings.get("urls") and not config.settings.get("sitemap_url"):
            raise ConnectorError("web connector needs 'urls' or 'sitemap_url'")
        self._client = client
        self._content: Dict[str, bytes] = {}

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0, follow_redirects=True,
                                             headers={"User-Agent": "Bodham/2.0 (+connector)", **self.config.settings.get("headers", {})})
        return self._client

    async def _urls(self) -> List[str]:
        urls = list(self.config.settings.get("urls") or [])
        sitemap = self.config.settings.get("sitemap_url")
        if sitemap:
            r = await self._http().get(sitemap)
            r.raise_for_status()
            urls.extend(_LOC.findall(r.text))
        limit = int(self.config.settings.get("max_pages", 500))
        seen, out = set(), []
        for u in urls:
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out[:limit]

    async def test_connection(self) -> Dict[str, Any]:
        urls = await self._urls()
        if not urls:
            raise ConnectorError("No URLs to crawl")
        r = await self._http().head(urls[0])
        return {"status": "ok", "urls": len(urls), "first_status": r.status_code}

    async def list_items(self) -> AsyncIterator[SourceItem]:
        for url in await self._urls():
            try:
                r = await self._http().get(url)
                r.raise_for_status()
            except Exception as exc:
                raise ConnectorError(f"GET {url} failed: {exc}")
            body = r.content
            ext = ext_of(urlparse(url).path.rsplit("/", 1)[-1] or "index.html", r.headers.get("content-type"))
            if ext not in ("pdf", "docx", "html", "md", "txt", "csv"):
                ext = "html"
            m = _TITLE.search(r.text) if ext == "html" else None
            title = (m.group(1).strip() if m else None) or (urlparse(url).path.strip("/").split("/")[-1] or urlparse(url).netloc)
            if ext == "html" and not title.lower().endswith(".html"):
                title = f"{title}.html"
            self._content[url] = body
            yield SourceItem(
                external_id=url, title=title[:200], file_type=ext, url=url, size=len(body),
                modified=datetime.now(timezone.utc), etag=r.headers.get("etag") or hashlib.sha1(body).hexdigest(),
                metadata={"content_type": r.headers.get("content-type")},
            )

    async def fetch(self, item: SourceItem) -> bytes:
        if item.external_id in self._content:
            return self._content.pop(item.external_id)
        r = await self._http().get(item.external_id)
        r.raise_for_status()
        return r.content

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
