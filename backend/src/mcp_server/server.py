from __future__ import annotations

import hmac
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Mapping, Optional

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field

from src.contracts import RetrievalFilters, RetrievalRequest
from src.core.config import settings
from src.core.logger import get_logger
from src.core.security import TokenData

logger = get_logger(__name__)

SERVER_NAME = "bodham"
SERVER_INSTRUCTIONS = (
    "Bodham is an enterprise knowledge retrieval engine. Call knowledge_retrieve with the user's question to get "
    "ranked evidence passages (with source, page and scores) from the indexed documents. Cite evidence by its "
    "source and page. The tool never synthesises an answer; do that yourself from the returned passages."
)


class MCPAuthError(ToolError):
    """Surfaces to the MCP client as an error result with the message intact."""


class EvidenceItem(BaseModel):
    id: str
    source: str
    page: Optional[int] = None
    document_id: Optional[str] = None
    content: str
    score: float = 0.0
    rerank_score: Optional[float] = None
    section: Optional[str] = None
    content_type: str = "text"


class RetrieveResult(BaseModel):
    query: str
    backend: str
    latency_ms: float
    context: str = ""
    evidence: List[EvidenceItem] = Field(default_factory=list)


class DocumentItem(BaseModel):
    document_id: str
    filename: str
    pages: Optional[int] = None
    chunks: Optional[int] = None
    created_at: Optional[str] = None


class DocumentsResult(BaseModel):
    documents: List[DocumentItem] = Field(default_factory=list)


class BackendsResult(BaseModel):
    default: str
    backends: List[Dict[str, Any]] = Field(default_factory=list)


def _bearer(headers: Optional[Mapping[str, str]]) -> Optional[str]:
    if not headers:
        return None
    auth = headers.get("authorization") or headers.get("Authorization")
    if not auth:
        return None
    parts = auth.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


class Caller:
    """Resolved MCP caller: a user identity, a trusted service, or anonymous."""

    def __init__(self, user: Optional[TokenData], service: bool):
        self.user = user
        self.service = service


def authenticate(headers: Optional[Mapping[str, str]]) -> Caller:
    """Resolve the caller from the Authorization header or raise ``MCPAuthError``."""
    token = _bearer(headers)
    if token is None:
        if settings.mcp_require_auth:
            raise MCPAuthError("Missing bearer token")
        return Caller(None, False)
    if settings.mcp_api_token and hmac.compare_digest(token, settings.mcp_api_token):
        return Caller(None, True)
    from src.core.auth import verify_bearer
    user = verify_bearer(token)
    if user is None:
        raise MCPAuthError("Invalid or expired token")
    return Caller(user, False)


def _access_filters(caller: Caller, document_ids: Optional[List[str]]) -> RetrievalFilters:
    from src.core.access import access_filters_for
    filters = access_filters_for(caller.user, service_caller=caller.service)
    filters.document_ids = document_ids or None
    return filters


def build_mcp_server() -> MCPServer:
    mcp = MCPServer(name=SERVER_NAME, instructions=SERVER_INSTRUCTIONS, version="2.0.0")

    @mcp.tool(
        name="knowledge_retrieve",
        description="Retrieve ranked evidence passages from the indexed knowledge base for a question. "
                    "Returns passages with source, page, scores and a pre-assembled numbered context.",
        structured_output=True,
    )
    async def knowledge_retrieve(
        query: str,
        ctx: Context,
        top_k: int = 8,
        document_ids: Optional[List[str]] = None,
        reasoning_effort: str = "low",
        backend: Optional[str] = None,
    ) -> RetrieveResult:
        caller = authenticate(ctx.headers)
        from src.knowledge import get_knowledge_adapter
        adapter = get_knowledge_adapter(backend)
        request = RetrievalRequest(
            query=query, top_k=max(1, min(int(top_k), 50)), reasoning_effort=reasoning_effort,  # type: ignore[arg-type]
            filters=_access_filters(caller, document_ids),
        )
        result = await adapter.retrieve(request)
        return RetrieveResult(
            query=result.query, backend=result.backend, latency_ms=result.latency_ms, context=result.context or "",
            evidence=[
                EvidenceItem(
                    id=f"ev_{i + 1}", source=c.source, page=c.page, document_id=c.document_id, content=c.content,
                    score=c.score, rerank_score=c.rerank_score,
                    section=" > ".join(c.section_path) if c.section_path else None, content_type=c.content_type,
                )
                for i, c in enumerate(result.chunks)
            ],
        )

    @mcp.tool(name="list_documents", description="List indexed documents visible to the caller.", structured_output=True)
    async def list_documents(ctx: Context, limit: int = 50) -> DocumentsResult:
        caller = authenticate(ctx.headers)
        from sqlalchemy import desc, select
        from src.core.access import document_visibility_clause
        from src.infrastructure.database import Document, session_scope
        async with session_scope() as db:
            q = select(Document).where(Document.status == "completed").order_by(desc(Document.created_at)).limit(max(1, min(limit, 500)))
            q = document_visibility_clause(q, caller.user, service_caller=caller.service)
            rows = (await db.execute(q)).scalars().all()
        return DocumentsResult(documents=[
            DocumentItem(document_id=str(d.id), filename=d.filename, pages=d.total_pages, chunks=d.chunks_count,
                         created_at=d.created_at.isoformat() if d.created_at else None)
            for d in rows
        ])

    @mcp.tool(name="list_backends", description="List configured knowledge backends and their capabilities.", structured_output=True)
    async def list_backends_tool(ctx: Context) -> BackendsResult:
        authenticate(ctx.headers)
        from src.knowledge import list_backends
        return BackendsResult(default=settings.knowledge_backend, backends=list_backends())

    return mcp


_server: Optional[MCPServer] = None


def get_mcp_server() -> MCPServer:
    """Current server instance (a fresh one is created for every host lifespan)."""
    global _server
    if _server is None:
        _server = build_mcp_server()
    return _server


def _build_http_app(server: MCPServer):
    return server.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )


class MCPMount:
    """ASGI app mounted at /mcp that forwards to the server created by the active lifespan.

    The SDK's session manager can only be run once per server instance, so each host
    lifespan builds a new MCPServer + transport app and swaps it in here.
    """

    def __init__(self) -> None:
        self.app = None

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "lifespan":   # the host app owns the lifespan
            return
        if self.app is None:
            from starlette.responses import JSONResponse
            await JSONResponse({"error": "MCP server not started"}, status_code=503)(scope, receive, send)
            return
        await self.app(scope, receive, send)


_mount = MCPMount()


def mcp_asgi_app() -> MCPMount:
    return _mount


@asynccontextmanager
async def mcp_lifespan() -> AsyncIterator[None]:
    """Create a fresh server + transport and run its session manager for the host's lifetime."""
    global _server
    _server = build_mcp_server()
    _mount.app = _build_http_app(_server)
    try:
        async with _server.session_manager.run():
            yield
    finally:
        _mount.app = None


def reset_mcp_server() -> None:
    global _server
    _server = None
    _mount.app = None
