"""
FastAPI dependency injection utilities.

Provides reusable dependencies for authentication, database sessions,
rate limiting, and service injection.
"""

from typing import Annotated, AsyncGenerator, Optional

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import redis.asyncio as redis

from .config import settings
from .logger import get_logger, set_request_context, generate_request_id
from .security import TokenData, verify_access_token

logger = get_logger(__name__)

# HTTP Bearer authentication scheme
security = HTTPBearer(auto_error=False)


# ==========================================
# Redis Connection
# ==========================================

_redis_client: Optional[redis.Redis] = None


async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    """
    Get Redis client instance.
    
    Yields:
        Redis client for caching and rate limiting
    """
    global _redis_client
    
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    
    try:
        yield _redis_client
    except Exception as e:
        logger.error("Redis connection error", error=str(e))
        raise


async def close_redis() -> None:
    """Close Redis connection on shutdown."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None


# ==========================================
# Authentication Dependencies
# ==========================================

async def get_current_user(
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials],
        Depends(security)
    ],
) -> TokenData:
    """
    Validate JWT token and return current user data.
    
    Args:
        credentials: HTTP Bearer credentials from request
        
    Returns:
        TokenData with user information
        
    Raises:
        HTTPException: If token is missing, invalid, or expired
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token_data = verify_access_token(credentials.credentials)
    
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return token_data


async def get_current_user_optional(
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials],
        Depends(security)
    ],
) -> Optional[TokenData]:
    """
    Optionally validate JWT token for routes that support anonymous access.
    
    Args:
        credentials: HTTP Bearer credentials from request (optional)
        
    Returns:
        TokenData if valid token provided, None for anonymous access
    """
    if credentials is None:
        return None
    
    return verify_access_token(credentials.credentials)


# Type aliases for cleaner dependency injection
CurrentUser = Annotated[TokenData, Depends(get_current_user)]
OptionalUser = Annotated[Optional[TokenData], Depends(get_current_user_optional)]
RedisClient = Annotated[redis.Redis, Depends(get_redis)]


# ==========================================
# Rate Limiting
# ==========================================

async def check_rate_limit(
    request: Request,
    redis_client: RedisClient,
    user: OptionalUser = None,
) -> None:
    """
    Check and enforce rate limiting using Redis.
    
    Args:
        request: FastAPI request object
        redis_client: Redis client for rate limit storage
        user: Optional authenticated user
        
    Raises:
        HTTPException: If rate limit exceeded
    """
    # Use user ID if authenticated, otherwise use client IP
    if user:
        identifier = f"rate_limit:user:{user.user_id}"
    else:
        client_ip = request.client.host if request.client else "unknown"
        identifier = f"rate_limit:ip:{client_ip}"
    
    try:
        # Get current request count
        current = await redis_client.get(identifier)
        
        if current is None:
            # First request - set counter with expiration
            await redis_client.setex(
                identifier,
                settings.rate_limit_window_seconds,
                1,
            )
        elif int(current) >= settings.rate_limit_requests:
            # Rate limit exceeded
            ttl = await redis_client.ttl(identifier)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {ttl} seconds.",
                headers={"Retry-After": str(ttl)},
            )
        else:
            # Increment counter
            await redis_client.incr(identifier)
    except redis.RedisError as e:
        # Log error but don't block request if Redis is unavailable
        logger.warning("Rate limiting unavailable", error=str(e))


RateLimited = Annotated[None, Depends(check_rate_limit)]


# ==========================================
# Request Context
# ==========================================

async def setup_request_context(
    request: Request,
    x_request_id: Annotated[Optional[str], Header()] = None,
    user: OptionalUser = None,
) -> str:
    """
    Set up request context for logging and tracing.
    
    Args:
        request: FastAPI request object
        x_request_id: Optional request ID from header
        user: Optional authenticated user
        
    Returns:
        The request ID for this request
    """
    # Use provided request ID or generate new one
    request_id = x_request_id or generate_request_id()
    user_id = user.user_id if user else ""
    
    # Set context for structured logging
    set_request_context(request_id, user_id)
    
    # Store in request state for access in endpoints
    request.state.request_id = request_id
    
    return request_id


RequestContext = Annotated[str, Depends(setup_request_context)]


# ==========================================
# Service Dependencies (to be expanded)
# ==========================================

# Placeholder for service dependencies
# These will be implemented in later phases

async def get_nvidia_llm_service():
    """Get NVIDIA LLM service instance."""
    from services.nvidia_llm_service import NvidiaLLMService
    return NvidiaLLMService()


async def get_embedding_service():
    """Get embedding service instance."""
    from services.embedding_service import EmbeddingService
    return EmbeddingService()


async def get_vector_store_service():
    """Get vector store service instance."""
    from services.vector_store_service import VectorStoreService
    return VectorStoreService()
