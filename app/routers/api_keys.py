import secrets
import string
import uuid

import bcrypt
from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.dependencies import CurrentUserDep, DatabaseDep
from app.models.organization import APIKey
from app.schemas.api_key import APIKeyCreate

router = APIRouter(prefix="/api/v1/api-keys", tags=["api-keys"])


def _serialize_api_key(key: APIKey, *, include_key: str | None = None) -> dict:
    data = {
        "id": str(key.id),
        "name": key.name,
        "prefix": key.prefix,
        "is_active": key.is_active,
        "created_at": key.created_at.isoformat() if key.created_at else None,
        "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
    }
    if include_key:
        data["key"] = include_key
    return data


@router.get("")
async def list_api_keys(user: CurrentUserDep, db: DatabaseDep):
    """List all API keys for the current organization."""
    result = await db.execute(
        select(APIKey)
        .where(APIKey.organization_id == user.organization_id)
        .order_by(APIKey.created_at.desc())
    )
    keys = result.scalars().all()
    return {"success": True, "data": [_serialize_api_key(k) for k in keys]}


@router.post("", status_code=201)
async def create_api_key(body: APIKeyCreate, user: CurrentUserDep, db: DatabaseDep):
    """Create a new API key. Returns the plain-text key ONCE."""
    prefix = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
    secret = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
    full_key = f"bc_live_{prefix}.{secret}"

    key_hash = bcrypt.hashpw(full_key.encode(), bcrypt.gensalt()).decode()

    api_key = APIKey(
        name=body.name,
        prefix=prefix,
        key_hash=key_hash,
        organization_id=user.organization_id,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return {"success": True, "data": _serialize_api_key(api_key, include_key=full_key)}


@router.delete("/{key_id}", status_code=204)
async def delete_api_key(key_id: uuid.UUID, user: CurrentUserDep, db: DatabaseDep):
    """Revoke/Delete an API key."""
    result = await db.execute(
        select(APIKey).where(
            APIKey.id == key_id,
            APIKey.organization_id == user.organization_id,
        )
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    await db.delete(api_key)
    await db.commit()
    return None
