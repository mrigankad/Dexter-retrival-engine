"""
Authentication routes for JWT token management.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from core.security import create_token_pair, verify_password, hash_password, verify_refresh_token, TokenPair
from core.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


class LoginRequest(BaseModel):
    """Login request model."""
    username: str
    password: str


class RegisterRequest(BaseModel):
    """User registration request model."""
    username: str
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """Token refresh request model."""
    refresh_token: str


class UserResponse(BaseModel):
    """User info response model."""
    user_id: str
    username: str
    email: Optional[str] = None


# Temporary in-memory user store (replace with DB in production)
_temp_users = {
    "admin": {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "username": "admin",
        "email": "admin@example.com",
        "password_hash": hash_password("admin123"),
    }
}


@router.post("/login", response_model=TokenPair)
async def login(request: LoginRequest):
    """
    Authenticate user and return JWT tokens.
    
    Returns access_token and refresh_token for authenticated sessions.
    """
    user = _temp_users.get(request.username)
    
    if not user or not verify_password(request.password, user["password_hash"]):
        logger.warning("Failed login attempt", username=request.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    
    tokens = create_token_pair(
        user_id=user["user_id"],
        username=user["username"],
        email=user["email"],
    )
    
    logger.info("User logged in", user_id=user["user_id"], username=user["username"])
    return tokens


@router.post("/register", response_model=UserResponse)
async def register(request: RegisterRequest):
    """
    Register a new user.
    
    Creates user account and returns user info.
    """
    if request.username in _temp_users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )
    
    import uuid
    user_id = str(uuid.uuid4())
    _temp_users[request.username] = {
        "user_id": user_id,
        "username": request.username,
        "email": request.email,
        "password_hash": hash_password(request.password),
    }
    
    logger.info("User registered", user_id=user_id, username=request.username)
    
    return UserResponse(
        user_id=user_id,
        username=request.username,
        email=request.email,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh_token(request: RefreshRequest):
    """
    Refresh access token using refresh token.
    
    Returns new token pair if refresh token is valid.
    """
    token_data = verify_refresh_token(request.refresh_token)
    
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    
    user = None
    for u in _temp_users.values():
        if u["user_id"] == token_data.user_id:
            user = u
            break
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    tokens = create_token_pair(
        user_id=user["user_id"],
        username=user["username"],
        email=user.get("email"),
    )
    
    logger.info("Token refreshed", user_id=user["user_id"])
    return tokens
