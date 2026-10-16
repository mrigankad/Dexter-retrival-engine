"""
Microsoft Foundry IQ / Azure AI Search agentic retrieval adapter.

Calls the knowledge base ``retrieve`` endpoint (REST 2026-04-01 GA / 2026-08-01-preview):

    POST {endpoint}/knowledgebases('{kb}')/retrieve?api-version=2026-08-01-preview
    {
      "messages": [{"role": "user", "content": [{"type": "text", "text": "..."}]}],
      "retrievalReasoningEffort": {"kind": "minimal|low|medium"},   # preview
      "outputMode": "extractiveData",                               # we synthesize ourselves
      "includeActivity": true, "includeReferences": true,
      "knowledgeSourceParams": [{"kind": "searchIndex", "knowledgeSourceName": "...",
                                 "filterAddOn": "tenant_id eq 't1'", "includeReferenceSourceData": true}],
      "maxRuntimeInSeconds": 30
    }

Response:
    {
      "response":   [{"content": [{"type": "text", "text": "<JSON array of {ref_id,title,terms,content}>"}]}],
      "activity":   [{"type": "modelQueryPlanning", "inputTokens": ..}, {"type": "searchIndex",
                      "searchIndexArguments": {"search": "..."}, "count": 12, "elapsedMs": 140}, ...],
      "references": [{"type": "searchIndex", "id": "0", "activitySource": 1, "docKey": "doc_17",
                      "rerankerScore": 3.5, "sourceData": {"chunk": "...", "title": "..."}}]
    }

Per-user ACL trimming: pass the caller's Entra token as ``filters.metadata["entra_token"]``
and it is sent in ``x-ms-query-source-authorization``. Each knowledge base is also an MCP
server at ``/knowledgebases/{kb}/mcp`` exposing ``knowledge_base_retrieve``.

The adapter maps ``references`` (preferred) or the JSON-encoded grounding
chunks in ``response[0].content[0].text`` into ``RetrievedChunk`` objects so
the orchestrator can synthesize once with our own citations.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

import httpx

from src.contracts import RetrievalRequest, RetrievalResult, RetrievedChunk
from src.core.config import settings
from src.core.logger import get_logger

from .base import AdapterCapabilities, KnowledgeAdapter

logger = get_logger(__name__)


class FoundryIQError(RuntimeError):
    pass


class FoundryIQAdapter(KnowledgeAdapter):
    name = "foundry_iq"

    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        bearer_token: Optional[str] = None,
        knowledge_base: Optional[str] = None,
        api_version: Optional[str] = None,
        knowledge_source: Optional[str] = None,
        path_style: str = "odata",
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.endpoint = (endpoint or settings.azure_search_endpoint).rstrip("/")
        self.api_key = api_key or settings.azure_search_api_key
        self.bearer_token = bearer_token or settings.azure_search_bearer_token
        self.knowledge_base = knowledge_base or settings.foundry_iq_knowledge_base
        self.api_version = api_version or settings.azure_search_api_version
        self.knowledge_source = knowledge_source or settings.foundry_iq_knowledge_source
        self.path_style = path_style   # odata: knowledgebases('kb') | plain: knowledgebases/kb | agents: agents/kb
        self._client = client

    # ── configuration ───────────────────────────────────────────────────

    @property
    def configured(self) -> bool:
        return bool(self.endpoint and self.knowledge_base and (self.api_key or self.bearer_token))

    def _headers(self, user_token: Optional[str] = None) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if user_token:
            # Foundry IQ trims results to the caller's document ACLs with this header.
            headers["x-ms-query-source-authorization"] = user_token
        if self.api_key:
            headers["api-key"] = self.api_key
        elif self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return headers

    def _resource(self, style: Optional[str] = None) -> str:
        style = style or self.path_style
        if style == "odata":
            return f"knowledgebases('{self.knowledge_base}')"
        if style == "agents":
            return f"agents/{self.knowledge_base}"
        return f"knowledgebases/{self.knowledge_base}"

    def _url(self, style: Optional[str] = None) -> str:
        return f"{self.endpoint}/{self._resource(style)}/retrieve?api-version={self.api_version}"

    @property
    def mcp_url(self) -> str:
        return f"{self.endpoint}/knowledgebases/{self.knowledge_base}/mcp?api-version={self.api_version}"

    def _client_or_new(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))
        return self._client

    # ── request building ───────────────────────────────────────────────

    def build_request_body(self, request: RetrievalRequest) -> Dict[str, Any]:
        messages = [{"role": "user", "content": [{"type": "text", "text": request.query}]}]
        for alt in request.alternate_queries[:2]:
            messages.append({"role": "user", "content": [{"type": "text", "text": alt}]})
        body: Dict[str, Any] = {
            "messages": messages,
            "retrievalReasoningEffort": {"kind": request.reasoning_effort or settings.foundry_iq_reasoning_effort},
            "outputMode": "extractiveData",   # single synthesis happens in our orchestrator
            "includeActivity": settings.foundry_iq_include_activity,
            "includeReferences": True,
            "maxRuntimeInSeconds": settings.foundry_iq_max_runtime_seconds,
        }
        # Security/scope filters are expressed as OData on a searchIndex knowledge source.
        odata = self._filters_to_odata(request)
        if odata or self.knowledge_source:
            param: Dict[str, Any] = {"kind": "searchIndex", "includeReferenceSourceData": True}
            if self.knowledge_source:
                param["knowledgeSourceName"] = self.knowledge_source
            if odata:
                param["filterAddOn"] = odata
            body["knowledgeSourceParams"] = [param]
        return body

    @staticmethod
    def _filters_to_odata(request: RetrievalRequest) -> Optional[str]:
        clauses: List[str] = []
        f = request.filters
        if f.tenant_id:
            clauses.append(f"tenant_id eq '{f.tenant_id}'")
        if f.document_ids:
            ids = ",".join(d.replace("'", "''") for d in f.document_ids)
            clauses.append(f"search.in(document_id, '{ids}', ',')")
        for key, value in (f.metadata or {}).items():
            if isinstance(value, str) and key != "entra_token":
                clauses.append(f"{key} eq '{value}'")
        return " and ".join(clauses) if clauses else None

    # ── response parsing ───────────────────────────────────────────────

    @staticmethod
    def parse_response(data: Dict[str, Any], query: str) -> List[RetrievedChunk]:
        chunks: List[RetrievedChunk] = []
        references = data.get("references") or []
        if references:
            for i, ref in enumerate(references):
                src = ref.get("sourceData") or {}
                text = src.get("chunk") or src.get("content") or src.get("text") or ""
                title = src.get("title") or src.get("metadata_storage_name") or ref.get("docKey") or f"reference-{i}"
                score = ref.get("rerankerScore") or ref.get("score") or 0.0
                chunks.append(RetrievedChunk(
                    id=str(ref.get("id", i)),
                    content=text,
                    score=float(score) / 4.0 if score and score > 1 else float(score or 0.0),
                    rerank_score=float(score) if score else None,
                    source=str(title),
                    document_id=ref.get("docKey") or src.get("document_id"),
                    page=src.get("page") or src.get("page_number"),
                    content_type="text",
                    backend="foundry_iq",
                    metadata={
                        "url": src.get("url") or src.get("metadata_storage_path"),
                        "activity_source": ref.get("activitySource"),
                        "type": ref.get("type"),
                    },
                ))
        else:
            # Fall back to the grounding text, which is a JSON array of {ref_id, title, terms, content}.
            response = data.get("response") or []
            for msg in response:
                for part in msg.get("content") or []:
                    text = part.get("text") if isinstance(part, dict) else None
                    if not text:
                        continue
                    try:
                        items = json.loads(text)
                    except json.JSONDecodeError:
                        chunks.append(RetrievedChunk(id="foundry_0", content=text, source="foundry_iq", backend="foundry_iq"))
                        continue
                    if isinstance(items, list):
                        for i, item in enumerate(items):
                            chunks.append(RetrievedChunk(
                                id=str(item.get("ref_id", i)),
                                content=item.get("content") or "",
                                source=item.get("title") or f"reference-{i}",
                                backend="foundry_iq",
                                metadata={"terms": item.get("terms")},
                            ))
        return [c for c in chunks if c.content.strip()]

    @staticmethod
    def executed_queries_from_activity(data: Dict[str, Any]) -> List[str]:
        out: List[str] = []
        for act in data.get("activity") or []:
            args = act.get("searchIndexArguments") or act.get("azureBlobArguments") or act.get("query") or {}
            if isinstance(args, dict) and args.get("search"):
                out.append(args["search"])
            elif isinstance(args, str):
                out.append(args)
        return out

    # ── public API ─────────────────────────────────────────────────────

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        if not self.configured:
            raise FoundryIQError(
                "Foundry IQ is not configured: set AZURE_SEARCH_ENDPOINT, FOUNDRY_IQ_KNOWLEDGE_BASE and "
                "AZURE_SEARCH_API_KEY (or AZURE_SEARCH_BEARER_TOKEN)"
            )
        started = time.perf_counter()
        body = self.build_request_body(request)
        headers = self._headers(user_token=request.filters.metadata.get("entra_token") if request.filters.metadata else None)

        response = await self._client_or_new().post(self._url(), headers=headers, json=body)
        if response.status_code == 404:
            # Try the other path styles once (older previews used /agents/{name}).
            for style in [s for s in ("odata", "plain", "agents") if s != self.path_style]:
                response = await self._client_or_new().post(self._url(style), headers=headers, json=body)
                if response.status_code != 404:
                    self.path_style = style
                    break
        if response.status_code >= 400:
            raise FoundryIQError(f"Foundry IQ retrieve failed {response.status_code}: {response.text[:400]}")
        data = response.json()
        chunks = self.parse_response(data, request.query)[: request.top_k]
        usage = {}
        for act in data.get("activity") or []:
            for key in ("inputTokens", "outputTokens"):
                if key in act:
                    usage[key] = usage.get(key, 0) + int(act[key] or 0)
        context = "\n\n---\n\n".join(f"[{i + 1}] {c.source}\n{c.content}" for i, c in enumerate(chunks))
        return RetrievalResult(
            query=request.query,
            chunks=chunks,
            backend=self.name,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            context=context,
            executed_queries=self.executed_queries_from_activity(data) or [request.query],
            metadata={"activity_steps": len(data.get("activity") or []), "usage": usage, "knowledge_base": self.knowledge_base},
        )

    async def healthcheck(self) -> Dict[str, Any]:
        if not self.configured:
            return {"backend": self.name, "status": "unconfigured"}
        try:
            url = f"{self.endpoint}/{self._resource()}?api-version={self.api_version}"
            r = await self._client_or_new().get(url, headers=self._headers())
            return {"backend": self.name, "status": "healthy" if r.status_code < 400 else "unhealthy", "http": r.status_code}
        except Exception as exc:
            return {"backend": self.name, "status": "unhealthy", "error": str(exc)}

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            hybrid_search=True, reranking=True, query_planning=True, multimodal=True,
            permission_filters=True, returns_context=True, ingestion=False,
        )
