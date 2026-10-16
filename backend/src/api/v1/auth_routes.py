"""JWT auth backed by the users table."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from src.core.dependency_injection import CurrentUser, DbSession
from src.core.logger import get_logger
from src.core.security import TokenPair, create_token_pair, hash_password, verify_password, verify_refresh_token
from src.infrastructure.database import User

router = APIRouter()
logger = get_logger(__name__)


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6)


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    user_id: str
    username: str
    email: Optional[str] = None
    role: str = "user"


@router.post("/login", response_model=TokenPair)
async def login(request: LoginRequest, db: DbSession):
    user = await db.scalar(select(User).where(User.username == request.username))
    if user is None or not user.is_active or not verify_password(request.password, user.password_hash):
        logger.warning("Failed login attempt", username=request.username)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    logger.info("User logged in", user_id=str(user.id))
    return create_token_pair(user_id=str(user.id), username=user.username, email=user.email)


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, db: DbSession):
    exists = await db.scalar(select(User).where((User.username == request.username) | (User.email == request.email)))
    if exists is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Username or email already exists")
    user = User(username=request.username, email=request.email, password_hash=hash_password(request.password))
    db.add(user)
    await db.flush()
    logger.info("User registered", user_id=str(user.id))
    return create_token_pair(user_id=str(user.id), username=user.username, email=user.email)


@router.post("/refresh", response_model=TokenPair)
async def refresh(request: RefreshRequest, db: DbSession):
    data = verify_refresh_token(request.refresh_token)
    if data is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")
    user = await db.scalar(select(User).where(User.username == data.username))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return create_token_pair(user_id=str(user.id), username=user.username, email=user.email)


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser, db: DbSession):
    row = await db.scalar(select(User).where(User.username == user.username))
    return UserResponse(user_id=user.user_id, username=user.username, email=user.email, role=getattr(row, "role", "user") or "user")
