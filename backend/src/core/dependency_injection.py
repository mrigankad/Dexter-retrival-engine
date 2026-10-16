"""FastAPI dependencies: auth, DB session, rate limiting, request context."""

from __future__ import annotations

from typing import Annotated, AsyncGenerator, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .logger import get_logger
from .security import TokenData
from .auth import verify_bearer

logger = get_logger(__name__)
security = HTTPBearer(auto_error=False)


# ── Database ───────────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    from src.infrastructure.database import get_session
    async for session in get_session():
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]


# ── Redis (optional) ───────────────────────────────────────────────────

async def get_redis():
    from src.infrastructure.cache import get_redis_client
    return get_redis_client()


async def close_redis() -> None:
    from src.infrastructure.cache import close_redis_client
    await close_redis_client()


# ── Authentication ─────────────────────────────────────────────────────

async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
) -> TokenData:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing authentication credentials",
                            headers={"WWW-Authenticate": "Bearer"})
    token_data = verify_bearer(credentials.credentials)
    if token_data is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token",
                            headers={"WWW-Authenticate": "Bearer"})
    return token_data


async def get_current_user_optional(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
) -> Optional[TokenData]:
    if credentials is None:
        return None
    return verify_bearer(credentials.credentials)


async def get_chat_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
) -> Optional[TokenData]:
    """Chat allows anonymous access only when ALLOW_ANONYMOUS_CHAT is true."""
    user = await get_current_user_optional(credentials)
    if user is None and not settings.allow_anonymous_chat:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


async def require_admin(user: Annotated[TokenData, Depends(get_current_user)]) -> TokenData:
    if (user.role or "").lower() != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    return user


CurrentUser = Annotated[TokenData, Depends(get_current_user)]
AdminUser = Annotated[TokenData, Depends(require_admin)]
OptionalUser = Annotated[Optional[TokenData], Depends(get_current_user_optional)]
ChatUser = Annotated[Optional[TokenData], Depends(get_chat_user)]


# ── Rate limiting (best effort, Redis-backed) ──────────────────────────

async def check_rate_limit(request: Request, user: OptionalUser = None) -> None:
    from src.infrastructure.cache import get_redis_client, redis_available
    if not await redis_available():
        return
    client = get_redis_client()
    identifier = f"rate_limit:user:{user.user_id}" if user else f"rate_limit:ip:{request.client.host if request.client else 'unknown'}"
    try:
        current = await client.incr(identifier)
        if current == 1:
            await client.expire(identifier, settings.rate_limit_window_seconds)
        if current > settings.rate_limit_requests:
            ttl = await client.ttl(identifier)
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Rate limit exceeded. Try again in {ttl} seconds.",
                                headers={"Retry-After": str(ttl)})
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Rate limiting unavailable", error=str(exc))


RateLimited = Annotated[None, Depends(check_rate_limit)]
