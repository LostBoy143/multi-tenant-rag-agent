import secrets
import string
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select

from app.auth.schemas import RegisterUserRequest
from app.auth.service import auth_service
from app.config import settings
from app.core.email import send_welcome_email
from app.dependencies import DatabaseDep, QdrantDep
from app.models.organization import Organization
from app.models.user import User
from app.schemas.organization import OrganizationCreate, OrganizationResponse
from app.services.vector_store import create_organization_collection

from app.services.vector_store import create_organization_collection
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

class ProvisionRequest(BaseModel):
    name: str
    slug: str
    admin_email: EmailStr

class SendWelcomeRequest(BaseModel):
    user_id: uuid.UUID
    temp_password: str

async def verify_admin_secret(
    db: DatabaseDep,
    x_admin_secret: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None
):
    # 1. Check Secret Header (Internal use)
    if x_admin_secret and x_admin_secret == settings.admin_secret:
        return True

    # 2. Check JWT Session (Dashboard use)
    from app.dependencies import get_current_user
    try:
        user = await get_current_user(db=db, authorization=authorization)
        if user.role == "superadmin" and user.email == settings.superadmin_email:
            return True
    except Exception:
        pass

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Forbidden: This area is restricted to the platform owner."
    )

AdminDep = Annotated[bool, Depends(verify_admin_secret)]

@router.post("/organizations", response_model=OrganizationResponse, status_code=201)
async def create_organization(
    body: OrganizationCreate,
    db: DatabaseDep,
    qdrant: QdrantDep,
    _: AdminDep
):
    """
    Internal admin endpoint to provision a new organization.
    Initializes a dedicated Qdrant collection for the org.
    """
    # Check if slug exists
    result = await db.execute(select(Organization).where(Organization.slug == body.slug))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Organization with this slug already exists")

    org = Organization(name=body.name, slug=body.slug)
    db.add(org)
    await db.commit()
    await db.refresh(org)

    # Initialize Qdrant collection
    await create_organization_collection(qdrant, org.id)

    return {"success": True, "data": {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "plan": org.plan,
        "created_at": org.created_at
    }}

@router.post("/provision", status_code=201)
async def provision_organization(
    body: ProvisionRequest,
    db: DatabaseDep,
    qdrant: QdrantDep,
    _: AdminDep
):
    """
    Atomic endpoint to create Org + Vector Coll + Admin User.
    Returns credentials without sending email.
    """
    # 1. Create Organization
    result = await db.execute(select(Organization).where(Organization.slug == body.slug))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Organization with this slug already exists")

    # verify email not taken
    result = await db.execute(select(User).where(User.email == body.admin_email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User with this email already exists")

    org = Organization(name=body.name, slug=body.slug)
    db.add(org)
    await db.flush() # Get ORG ID

    # 2. Initialize Qdrant
    await create_organization_collection(qdrant, org.id)

    # 3. Create Admin User
    temp_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
    user = User(
        email=body.admin_email,
        password_hash=auth_service.hash_password(temp_password),
        organization_id=org.id,
        role="admin", # Default for new org
        must_change_password=True
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {"success": True, "data": {
        "organization": {
            "id": org.id,
            "name": org.name,
            "slug": org.slug
        },
        "user": {
            "id": user.id,
            "email": user.email,
            "temp_password": temp_password
        }
    }}

@router.post("/send-welcome")
async def send_manual_welcome(
    body: SendWelcomeRequest,
    db: DatabaseDep,
    _: AdminDep
):
    """Manual trigger to send welcome email once provisioning is confirmed by human admin."""
    result = await db.execute(select(User).where(User.id == body.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    await send_welcome_email(user.email, body.temp_password)
    return {"success": True, "message": f"Welcome email sent to {user.email}"}

@router.get("/organizations")
async def list_organizations(
    db: DatabaseDep,
    _: AdminDep
):
    """List all organizations with basic counts."""
    from sqlalchemy import func
    from app.models.agent import Agent
    from app.models.document import Document

    # Subqueries for counts
    result = await db.execute(select(Organization).order_by(Organization.created_at.desc()))
    orgs = result.scalars().all()
    
    data = []
    for org in orgs:
        # Simple count for now, optimization later if needed
        agent_res = await db.execute(select(func.count()).select_from(Agent).where(Agent.organization_id == org.id))
        user_res = await db.execute(select(func.count()).select_from(User).where(User.organization_id == org.id))
        doc_res = await db.execute(select(func.count()).select_from(Document).where(Document.organization_id == org.id))
        
        data.append({
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "plan": org.plan,
            "created_at": org.created_at,
            "stats": {
                "agents": agent_res.scalar(),
                "users": user_res.scalar(),
                "documents": doc_res.scalar()
            }
        })

    return {"success": True, "data": data}
