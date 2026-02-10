"""
Security utilities for JWT authentication and password hashing.

Provides secure token generation, validation, and password management
for the RAG backend API.
"""

from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel

from .config import settings


class TokenData(BaseModel):
    """JWT token payload data."""
    user_id: str
    username: str
    email: Optional[str] = None
    exp: datetime
    token_type: str = "access"


class TokenPair(BaseModel):
    """Access and refresh token pair."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a hashed password.
    
    Args:
        plain_password: The plain text password
        hashed_password: The bcrypt hashed password
        
    Returns:
        True if passwords match, False otherwise
    """
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.
    
    Args:
        password: Plain text password to hash
        
    Returns:
        Bcrypt hashed password
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def create_access_token(
    user_id: str,
    username: str,
    email: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT access token.
    
    Args:
        user_id: User's unique identifier
        username: User's username
        email: User's email (optional)
        expires_delta: Custom expiration time (optional)
        
    Returns:
        Encoded JWT access token
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.jwt_access_token_expire_minutes
        )
    
    payload = {
        "sub": user_id,
        "username": username,
        "email": email,
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access",
    }
    
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(
    user_id: str,
    username: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT refresh token.
    
    Args:
        user_id: User's unique identifier
        username: User's username
        expires_delta: Custom expiration time (optional)
        
    Returns:
        Encoded JWT refresh token
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            days=settings.jwt_refresh_token_expire_days
        )
    
    payload = {
        "sub": user_id,
        "username": username,
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh",
    }
    
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_token_pair(
    user_id: str,
    username: str,
    email: Optional[str] = None,
) -> TokenPair:
    """
    Create both access and refresh tokens.
    
    Args:
        user_id: User's unique identifier
        username: User's username
        email: User's email (optional)
        
    Returns:
        TokenPair with access_token, refresh_token, and metadata
    """
    access_token = create_access_token(user_id, username, email)
    refresh_token = create_refresh_token(user_id, username)
    
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


def decode_token(token: str) -> Optional[TokenData]:
    """
    Decode and validate a JWT token.
    
    Args:
        token: The JWT token to decode
        
    Returns:
        TokenData if valid, None if invalid or expired
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        
        user_id: str = payload.get("sub")
        username: str = payload.get("username")
        email: str = payload.get("email")
        exp: datetime = datetime.fromtimestamp(payload.get("exp"))
        token_type: str = payload.get("type", "access")
        
        if user_id is None or username is None:
            return None
        
        return TokenData(
            user_id=user_id,
            username=username,
            email=email,
            exp=exp,
            token_type=token_type,
        )
    except JWTError:
        return None


def verify_access_token(token: str) -> Optional[TokenData]:
    """
    Verify an access token is valid and not expired.
    
    Args:
        token: The access token to verify
        
    Returns:
        TokenData if valid access token, None otherwise
    """
    token_data = decode_token(token)
    
    if token_data is None:
        return None
    
    if token_data.token_type != "access":
        return None
    
    if token_data.exp < datetime.utcnow():
        return None
    
    return token_data


def verify_refresh_token(token: str) -> Optional[TokenData]:
    """
    Verify a refresh token is valid and not expired.
    
    Args:
        token: The refresh token to verify
        
    Returns:
        TokenData if valid refresh token, None otherwise
    """
    token_data = decode_token(token)
    
    if token_data is None:
        return None
    
    if token_data.token_type != "refresh":
        return None
    
    if token_data.exp < datetime.utcnow():
        return None
    
    return token_data


def extract_token_from_header(authorization: str) -> Optional[str]:
    """
    Extract JWT token from Authorization header.
    
    Args:
        authorization: The Authorization header value (e.g., "Bearer <token>")
        
    Returns:
        The token string if valid format, None otherwise
    """
    if not authorization:
        return None
    
    parts = authorization.split()
    
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    
    return parts[1]
