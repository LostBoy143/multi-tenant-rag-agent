from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt

from app.config import settings

def sign_access_token(data: dict[str, Any]) -> str:
    """Issue a short-lived access token (15 min)."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)

def sign_refresh_token(data: dict[str, Any]) -> str:
    """Issue a long-lived refresh token (7 days)."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)

def verify_token(token: str) -> dict[str, Any]:
    """Verify any JWT and return payload."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload
    except Exception:
        # We'll handle specific exceptions in dependency layer
        raise
