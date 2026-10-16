"""
MCP (Model Context Protocol) server: exposes Bodham as a knowledge source.

Mounted at ``/mcp`` (streamable HTTP, stateless). Tools:
  knowledge_retrieve(query, top_k, document_ids, reasoning_effort, backend) -> evidence
  list_documents(limit)                                                      -> indexed documents
  list_backends()                                                            -> configured knowledge backends

Auth: a bearer token is required unless MCP_REQUIRE_AUTH=false. Accepted tokens are
Bodham access JWTs or the static MCP_API_TOKEN. The caller's identity derives the
same mandatory access filters as the HTTP API.
"""

from .server import build_mcp_server, get_mcp_server, mcp_asgi_app, mcp_lifespan

__all__ = ["build_mcp_server", "get_mcp_server", "mcp_asgi_app", "mcp_lifespan"]
