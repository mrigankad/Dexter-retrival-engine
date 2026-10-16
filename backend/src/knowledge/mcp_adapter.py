"""
Generic MCP client adapter: use any MCP knowledge server as a backend.

Works with Bodham's own /mcp (tool ``knowledge_retrieve``), Microsoft Foundry IQ
(``/knowledgebases/{kb}/mcp``, tool ``knowledge_base_retrieve``), Qdrant MCP,
Pinecone Assistant, Ragie, Mixedbread, Glean, etc. The tool result is parsed
defensively: structured content first, then JSON text, then plain text.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from src.contracts import RetrievalRequest, RetrievalResult, RetrievedChunk
from src.core.config import settings
from src.core.logger import get_logger

from .base import AdapterCapabilities, KnowledgeAdapter

logger = get_logger(__name__)


class McpKnowledgeAdapter(KnowledgeAdapter):
    name = "mcp"

    def __init__(
        self,
        server: Any = None,                 # URL string, Transport, or an in-process MCPServer (tests)
        tool_name: Optional[str] = None,
        query_arg: Optional[str] = None,
        auth_token: Optional[str] = None,
        extra_args: Optional[Dict[str, Any]] = None,
    ):
        self.server = server if server is not None else settings.mcp_server_url
        self.tool_name = tool_name or settings.mcp_tool_name
        self.query_arg = query_arg or settings.mcp_query_arg
        self.auth_token = auth_token if auth_token is not None else settings.mcp_auth_token
        self.extra_args = extra_args or {}
        self._tools_cache: Optional[List[str]] = None

    @property
    def configured(self) -> bool:
        return bool(self.server)

    # ── transport ──────────────────────────────────────────────────────

    def _client(self):
        from mcp.client.client import Client
        if isinstance(self.server, str):
            if self.auth_token:
                import httpx2
                from mcp.client.streamable_http import streamable_http_client
                http = httpx2.AsyncClient(headers={"Authorization": f"Bearer {self.auth_token}"},
                                          timeout=httpx2.Timeout(settings.mcp_timeout, connect=10.0))
                return Client(streamable_http_client(self.server, http_client=http))
            return Client(self.server)
        return Client(self.server)

    # ── argument building ──────────────────────────────────────────────

    def build_arguments(self, request: RetrievalRequest) -> Dict[str, Any]:
        args: Dict[str, Any] = {self.query_arg: request.query, **self.extra_args}
        if self.tool_name == "knowledge_retrieve":           # Bodham-to-Bodham federation
            args.update({"top_k": request.top_k, "reasoning_effort": request.reasoning_effort})
            if request.filters.document_ids:
                args["document_ids"] = list(request.filters.document_ids)
        elif self.tool_name == "knowledge_base_retrieve":    # Foundry IQ MCP tool takes the conversation
            args.setdefault("messages", [{"role": "user", "content": [{"type": "text", "text": request.query}]}])
        return args

    # ── result parsing ─────────────────────────────────────────────────

    @staticmethod
    def _items_from(payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, dict):
            for key in ("evidence", "chunks", "results", "references", "items", "documents", "passages", "hits"):
                if isinstance(payload.get(key), list):
                    return [x for x in payload[key] if isinstance(x, dict)]
            if "content" in payload or "text" in payload:
                return [payload]
            return []
        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)]
        return []

    @classmethod
    def parse_result(cls, result: Any, backend: str = "mcp") -> List[RetrievedChunk]:
        payload: Any = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
        if isinstance(payload, dict) and set(payload) == {"result"}:   # SDK wraps bare dict/list returns
            payload = payload["result"]
        texts: List[str] = []
        if payload is None:
            for block in getattr(result, "content", None) or []:
                text = getattr(block, "text", None)
                if text is None and isinstance(block, dict):
                    text = block.get("text")
                if text:
                    texts.append(text)
            for text in texts:
                try:
                    payload = json.loads(text)
                    break
                except (json.JSONDecodeError, TypeError):
                    continue
        items = cls._items_from(payload)
        chunks: List[RetrievedChunk] = []
        if items:
            for i, item in enumerate(items):
                src = item.get("sourceData") or {}
                content = item.get("content") or item.get("text") or item.get("chunk") or src.get("chunk") or src.get("content") or ""
                if not isinstance(content, str) or not content.strip():
                    continue
                score = item.get("rerank_score") if item.get("rerank_score") is not None else item.get("score", item.get("rerankerScore", 0.0))
                chunks.append(RetrievedChunk(
                    id=str(item.get("id", item.get("ref_id", i))), content=content,
                    score=float(item.get("score") or 0.0), rerank_score=float(score) if score is not None else None,
                    source=str(item.get("source") or item.get("title") or src.get("title") or item.get("docKey") or f"reference-{i}"),
                    document_id=item.get("document_id") or item.get("docKey"), page=item.get("page") or src.get("page"),
                    content_type=str(item.get("content_type") or "text"), backend=backend,
                    metadata={k: v for k, v in item.items() if k not in {"content", "text", "chunk", "score", "rerank_score", "source", "title", "page", "document_id", "id"}},
                ))
        elif texts:
            for i, text in enumerate(texts):
                if text.strip():
                    chunks.append(RetrievedChunk(id=f"mcp_{i}", content=text, source="mcp", backend=backend))
        return chunks

    # ── public API ─────────────────────────────────────────────────────

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        if not self.configured:
            raise RuntimeError("MCP backend is not configured: set MCP_SERVER_URL (and MCP_TOOL_NAME / MCP_AUTH_TOKEN)")
        started = time.perf_counter()
        async with self._client() as client:
            result = await client.call_tool(self.tool_name, self.build_arguments(request))
        if getattr(result, "is_error", False) or getattr(result, "isError", False):
            text = " ".join(getattr(b, "text", "") for b in (result.content or []))
            raise RuntimeError(f"MCP tool {self.tool_name} failed: {text[:300]}")
        chunks = self.parse_result(result, backend=self.name)[: request.top_k]
        payload = getattr(result, "structured_content", None) or {}
        if isinstance(payload, dict) and set(payload) == {"result"}:
            payload = payload["result"]
        context = payload.get("context") if isinstance(payload, dict) else None
        if not context:
            context = "\n\n---\n\n".join(f"[{i + 1}] {c.source}\n{c.content}" for i, c in enumerate(chunks))
        return RetrievalResult(
            query=request.query, chunks=chunks, backend=self.name,
            latency_ms=round((time.perf_counter() - started) * 1000, 1), context=context,
            executed_queries=[request.query],
            metadata={"tool": self.tool_name, "server": self.server if isinstance(self.server, str) else "in-process",
                      "remote_backend": payload.get("backend") if isinstance(payload, dict) else None},
        )

    async def healthcheck(self) -> Dict[str, Any]:
        if not self.configured:
            return {"backend": self.name, "status": "unconfigured"}
        try:
            async with self._client() as client:
                tools = await client.list_tools()
                names = [t.name for t in tools.tools]
            ok = self.tool_name in names
            return {"backend": self.name, "status": "healthy" if ok else "unhealthy", "tools": names,
                    "detail": None if ok else f"tool {self.tool_name} not exposed"}
        except Exception as exc:
            return {"backend": self.name, "status": "unhealthy", "error": str(exc)}

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(hybrid_search=True, reranking=True, query_planning=self.tool_name == "knowledge_base_retrieve",
                                   permission_filters=True, returns_context=True, ingestion=False)
