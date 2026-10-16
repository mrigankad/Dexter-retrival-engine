"""
Access control helpers: derive mandatory retrieval filters from the *verified* identity.

Principals are strings stored on every chunk payload (``acl`` list) and every document:
    public                 anyone (including anonymous callers when ALLOW_ANONYMOUS_CHAT)
    tenant:<tenant_id>     everyone in the tenant
    user:<user_id>         the owner
    group:<name>           members of a group (from the token's ``groups`` claim)

Rules
* The filter is always built server-side from the token; client-supplied user ids are ignored.
* Anonymous callers see only ``public`` documents (fail closed).
* Admins and trusted service callers (MCP_API_TOKEN) see everything in their tenant scope.
"""

from __future__ import annotations

from typing import List, Optional

from src.contracts import RetrievalFilters
from src.core.config import settings
from src.core.security import TokenData

PUBLIC = "public"


def principals_for(user: Optional[TokenData]) -> List[str]:
    if user is None:
        return [PUBLIC]
    out = [PUBLIC, f"user:{user.user_id}"]
    if user.tenant_id:
        out.append(f"tenant:{user.tenant_id}")
    out.extend(f"group:{g}" for g in (user.groups or []))
    return out


def acl_for_document(owner_id: Optional[str], tenant_id: Optional[str], visibility: str, groups: Optional[List[str]] = None) -> List[str]:
    """Principals allowed to see a document given its visibility setting."""
    acl: List[str] = []
    if owner_id:
        acl.append(f"user:{owner_id}")
    if visibility == "public":
        acl.append(PUBLIC)
    elif visibility == "tenant" and tenant_id:
        acl.append(f"tenant:{tenant_id}")
    for g in groups or []:
        acl.append(f"group:{g}")
    if not acl:
        acl.append(PUBLIC if visibility == "public" else f"user:{owner_id or 'nobody'}")
    return sorted(set(acl))


def is_admin(user: Optional[TokenData]) -> bool:
    return user is not None and (user.role or "").lower() == "admin"


def access_filters_for(user: Optional[TokenData], service_caller: bool = False) -> RetrievalFilters:
    """Mandatory filters for retrieval. Admins/service callers are tenant-scoped only."""
    if not settings.acl_enforcement:
        return RetrievalFilters()
    if service_caller or is_admin(user):
        return RetrievalFilters(tenant_id=user.tenant_id if user and user.tenant_id and settings.acl_tenant_scoping else None)
    return RetrievalFilters(principals=principals_for(user))


def document_visibility_clause(query, user: Optional[TokenData], service_caller: bool = False):
    """Apply the same visibility rule to a SQLAlchemy ``select(Document)``."""
    from sqlalchemy import or_
    from src.infrastructure.database import Document
    if not settings.acl_enforcement or service_caller or is_admin(user):
        return query
    allowed = principals_for(user)
    conditions = [Document.visibility == "public"]
    if user is not None:
        import uuid
        try:
            conditions.append(Document.user_id == uuid.UUID(user.user_id))
        except ValueError:
            pass
        if user.tenant_id:
            conditions.append((Document.visibility == "tenant") & (Document.tenant_id == user.tenant_id))
        for g in user.groups or []:
            conditions.append(Document.shared_groups.like(f"%,{g},%"))
    return query.where(or_(*conditions))


def groups_to_column(groups: Optional[List[str]]) -> str:
    cleaned = sorted({g.strip() for g in (groups or []) if g and g.strip()})
    return f",{','.join(cleaned)}," if cleaned else ""


def column_to_groups(value: Optional[str]) -> List[str]:
    return [g for g in (value or "").split(",") if g]
