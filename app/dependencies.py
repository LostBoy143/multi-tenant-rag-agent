from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID

import bcrypt
from fastapi import Depends, Header, HTTPException, status, Cookie
from jose import JWTError
from qdrant_client import AsyncQdrantClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import verify_token
from app.config import settings
from app.core.redis import redis_client
from app.database import async_session_factory
from app.models import APIKey, Organization, User

async def get_redis_client():
    return redis_client


async def get_db():
    async with async_session_factory() as session:
        yield session


DatabaseDep = Annotated[AsyncSession, Depends(get_db)]

_qdrant_client: AsyncQdrantClient | None = None


async def get_qdrant() -> AsyncQdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        if settings.qdrant_url and settings.qdrant_api_key:
            _qdrant_client = AsyncQdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key
            )
        else:
            _qdrant_client = AsyncQdrantClient(
                host=settings.qdrant_host, port=settings.qdrant_port
            )
    return _qdrant_client


QdrantDep = Annotated[AsyncQdrantClient, Depends(get_qdrant)]


async def get_current_user(
    db: DatabaseDep,
    access_token: Annotated[str | None, Cookie(alias="accessToken")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """
    JWT Authentication dependency.
    Checks for token in 'accessToken' cookie OR 'Authorization: Bearer <token>' header.
    """
    token = None
    if access_token:
        token = access_token
    elif authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Missing token.",
        )

    try:
        payload = verify_token(token)
        user_id_str: str = payload.get("sub")
        token_type: str = payload.get("type")
        
        if token_type != "access" or user_id_str is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload.",
            )
            
        user_id = UUID(user_id_str)
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
        )

    result = await db.execute(select(User).where(User.id == user_id, User.is_active.is_(True)))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive.",
        )

    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def get_current_tenant(
    db: DatabaseDep,
    x_api_key: Annotated[str, Header()],
) -> Organization:
    """
    API Key Authentication dependency for public widget endpoints.
    """
    if not x_api_key or len(x_api_key) < 10:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format.",
        )

    # Keys are stored as bc_live_{prefix}.{secret}; DB stores only the 8-char prefix
    raw_prefix = x_api_key.split(".")[0] if "." in x_api_key else x_api_key[:8]
    prefix = raw_prefix.replace("bc_live_", "")

    result = await db.execute(
        select(APIKey).where(APIKey.prefix == prefix, APIKey.is_active.is_(True))
    )
    api_key_row = result.scalar_one_or_none()

    if api_key_row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    if not bcrypt.checkpw(x_api_key.encode(), api_key_row.key_hash.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    # Check expiration if set
    if api_key_row.expires_at and api_key_row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has expired.",
        )

    # Update last_used_at
    api_key_row.last_used_at = datetime.now(timezone.utc)
    await db.commit()

    result = await db.execute(select(Organization).where(Organization.id == api_key_row.organization_id))
    org = result.scalar_one_or_none()

    if org is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Organization not found.",
        )

    return org


CurrentTenantDep = Annotated[Organization, Depends(get_current_tenant)]
