import secrets
import string
import uuid
from typing import List

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.dependencies import CurrentUserDep, DatabaseDep
from app.models.organization import APIKey
from app.schemas.api_key import APIKeyCreate, APIKeyResponse, APIKeySecretResponse

router = APIRouter(prefix="/api/v1/api-keys", tags=["api-keys"])


@router.get("")
async def list_api_keys(
    user: CurrentUserDep,
    db: DatabaseDep
):
    """List all API keys for the current organization."""
    result = await db.execute(
        select(APIKey)
        .where(APIKey.organization_id == user.organization_id)
        .order_by(APIKey.created_at.desc())
    )
    keys = result.scalars().all()
    return {"success": True, "data": keys}


@router.post("", response_model=APIKeySecretResponse, status_code=201)
async def create_api_key(
    body: APIKeyCreate,
    user: CurrentUserDep,
    db: DatabaseDep
):
    """
    Create a new API key for the organization.
    Returns the plain-text key ONCE.
    """
    # 1. Generate key: bc_live_<prefix>.<secret>
    prefix = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
    secret = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
    full_key = f"bc_live_{prefix}.{secret}"
    
    # 2. Hash the exact key
    key_hash = bcrypt.hashpw(full_key.encode(), bcrypt.gensalt()).decode()
    
    api_key = APIKey(
        name=body.name,
        prefix=prefix,
        key_hash=key_hash,
        organization_id=user.organization_id
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    
    # 3. Return response with full key
    data = APIKeySecretResponse(
        id=api_key.id,
        name=api_key.name,
        prefix=api_key.prefix,
        isActive=api_key.is_active,
        createdAt=api_key.created_at,
        lastUsedAt=api_key.last_used_at,
        key=full_key
    )
    return {"success": True, "data": data}


@router.delete("/{key_id}", status_code=204)
async def delete_api_key(
    key_id: uuid.UUID,
    user: CurrentUserDep,
    db: DatabaseDep
):
    """Revoke/Delete an API key."""
    result = await db.execute(
        select(APIKey).where(
            APIKey.id == key_id, 
            APIKey.organization_id == user.organization_id
        )
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    await db.delete(api_key)
    await db.commit()
    return None
