import secrets
import uuid

import bcrypt
from fastapi import APIRouter

from app.dependencies import CurrentTenantDep, DatabaseDep, QdrantDep
from app.models.tenant import APIKey, Tenant
from app.schemas.tenant import TenantCreate, TenantResponse, TenantWithKeyResponse
from app.services.vector_store import create_tenant_collection

router = APIRouter(prefix="/api/v1/tenants", tags=["tenants"])


@router.post("", status_code=201)
async def register_tenant(
    body: TenantCreate,
    db: DatabaseDep,
    qdrant: QdrantDep,
) -> TenantWithKeyResponse:
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name=body.name)
    db.add(tenant)

    raw_key = f"{secrets.token_hex(4)}.{secrets.token_hex(24)}"
    prefix = raw_key[:8]
    key_hash = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()

    api_key = APIKey(
        tenant_id=tenant_id,
        key_hash=key_hash,
        prefix=prefix,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(tenant)

    await create_tenant_collection(qdrant, tenant_id)

    return TenantWithKeyResponse(
        tenant=TenantResponse(
            id=tenant.id,
            name=tenant.name,
            created_at=tenant.created_at,
        ),
        api_key=raw_key,
    )


@router.get("/me")
async def get_current_tenant_info(tenant: CurrentTenantDep) -> TenantResponse:
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        created_at=tenant.created_at,
    )
