"""
Bearer-token verification for every entry point (HTTP API, MCP server).

AUTH_MODE=local  : Bodham-issued HS256 JWTs (see security.py)
AUTH_MODE=entra  : Microsoft Entra ID access tokens (RS256, validated against the tenant JWKS)
AUTH_MODE=both   : try local first, then Entra
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from jose import JWTError, jwt

from src.core.config import settings
from src.core.logger import get_logger
from src.core.security import TokenData, verify_access_token

logger = get_logger(__name__)


class JWKSCache:
    """Fetches and caches the tenant's signing keys (refreshed on unknown kid or every hour)."""

    def __init__(self, url: str, ttl_seconds: int = 3600):
        self.url = url
        self.ttl = ttl_seconds
        self._keys: Dict[str, Dict[str, Any]] = {}
        self._fetched_at = 0.0

    def set_keys(self, jwks: Dict[str, Any]) -> None:
        self._keys = {k["kid"]: k for k in jwks.get("keys", []) if k.get("kid")}
        self._fetched_at = time.time()

    def _refresh(self) -> None:
        response = httpx.get(self.url, timeout=10.0)
        response.raise_for_status()
        self.set_keys(response.json())

    def get(self, kid: str) -> Optional[Dict[str, Any]]:
        if kid not in self._keys or time.time() - self._fetched_at > self.ttl:
            try:
                self._refresh()
            except Exception as exc:
                logger.warning("JWKS refresh failed", url=self.url, error=str(exc))
        return self._keys.get(kid)


_jwks: Optional[JWKSCache] = None
_jwks_injected = False


def entra_jwks_url() -> str:
    return settings.entra_jwks_url or f"https://login.microsoftonline.com/{settings.entra_tenant_id or 'common'}/discovery/v2.0/keys"


def entra_issuer() -> str:
    return settings.entra_issuer or f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0"


def get_jwks_cache() -> JWKSCache:
    global _jwks
    if _jwks is None or (not _jwks_injected and _jwks.url != entra_jwks_url()):
        _jwks = JWKSCache(entra_jwks_url())
    return _jwks


def set_jwks_cache(cache: Optional[JWKSCache]) -> None:
    """Inject a pre-populated cache (tests, air-gapped deployments). ``None`` restores the default."""
    global _jwks, _jwks_injected
    _jwks = cache
    _jwks_injected = cache is not None


def verify_entra_token(token: str) -> Optional[TokenData]:
    """Validate an Entra ID access/ID token and map its claims to TokenData."""
    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
        return None
    kid = header.get("kid")
    if not kid:
        return None
    key = get_jwks_cache().get(kid)
    if key is None:
        return None
    options = {"verify_aud": bool(settings.entra_client_id), "verify_iss": bool(settings.entra_tenant_id or settings.entra_issuer)}
    try:
        claims = jwt.decode(
            token, key, algorithms=[header.get("alg", "RS256")],
            audience=settings.entra_client_id or None,
            issuer=entra_issuer() if options["verify_iss"] else None,
            options=options,
        )
    except JWTError as exc:
        logger.info("Entra token rejected", error=str(exc))
        return None
    oid = claims.get("oid") or claims.get("sub")
    if not oid:
        return None
    groups: List[str] = [str(g) for g in (claims.get("groups") or [])]
    roles: List[str] = [str(r) for r in (claims.get("roles") or [])]
    role = "admin" if (settings.entra_admin_group and settings.entra_admin_group in groups) or "admin" in [r.lower() for r in roles] else "user"
    return TokenData(
        user_id=str(oid),
        username=claims.get("preferred_username") or claims.get("upn") or claims.get("email") or str(oid),
        email=claims.get("email") or claims.get("preferred_username"),
        exp=datetime.utcfromtimestamp(int(claims.get("exp", 0))),
        token_type="access",
        tenant_id=claims.get("tid") or settings.entra_tenant_id or None,
        role=role,
        groups=groups,
        issuer="entra",
    )


def verify_bearer(token: str) -> Optional[TokenData]:
    """Verify a bearer token according to AUTH_MODE."""
    mode = settings.auth_mode
    if mode in ("local", "both"):
        user = verify_access_token(token)
        if user is not None:
            return user
    if mode in ("entra", "both"):
        return verify_entra_token(token)
    return None
