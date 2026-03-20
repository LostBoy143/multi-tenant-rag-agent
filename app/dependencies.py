from typing import Annotated

import bcrypt
from fastapi import Depends, Header, HTTPException, status
from qdrant_client import AsyncQdrantClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory
from app.models.tenant import APIKey, Tenant


async def get_db():
    async with async_session_factory() as session:
        yield session


DatabaseDep = Annotated[AsyncSession, Depends(get_db)]

_qdrant_client: AsyncQdrantClient | None = None


async def get_qdrant() -> AsyncQdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = AsyncQdrantClient(
            host=settings.qdrant_host, port=settings.qdrant_port
        )
    return _qdrant_client


QdrantDep = Annotated[AsyncQdrantClient, Depends(get_qdrant)]


async def get_current_tenant(
    db: DatabaseDep,
    x_api_key: Annotated[str, Header()],
) -> Tenant:
    if not x_api_key or len(x_api_key) < 10:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    prefix = x_api_key[:8]
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

    result = await db.execute(select(Tenant).where(Tenant.id == api_key_row.tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant not found.",
        )

    return tenant


CurrentTenantDep = Annotated[Tenant, Depends(get_current_tenant)]
