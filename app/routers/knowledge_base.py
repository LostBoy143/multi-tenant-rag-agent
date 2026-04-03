import uuid
from typing import List, Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.dependencies import CurrentUserDep, DatabaseDep
from app.models.knowledge_base import KnowledgeBase
from app.schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseResponse

router = APIRouter(prefix="/api/v1/knowledge-bases", tags=["knowledge-bases"])


@router.get("")
async def list_knowledge_bases(
    user: CurrentUserDep,
    db: DatabaseDep
):
    """List all knowledge bases for the current organization."""
    result = await db.execute(
        select(KnowledgeBase)
        .where(KnowledgeBase.organization_id == user.organization_id)
        .order_by(KnowledgeBase.created_at.desc())
    )
    kbs = result.scalars().all()
    return {"success": True, "data": kbs}


@router.post("", response_model=KnowledgeBaseResponse, status_code=201)
async def create_knowledge_base(
    body: KnowledgeBaseCreate,
    user: CurrentUserDep,
    db: DatabaseDep
):
    """Create a new knowledge base container for documents."""
    kb = KnowledgeBase(
        name=body.name,
        organization_id=user.organization_id
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    return kb


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base(
    kb_id: uuid.UUID,
    user: CurrentUserDep,
    db: DatabaseDep
):
    """Get details of a specific knowledge base."""
    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id, 
            KnowledgeBase.organization_id == user.organization_id
        )
    )
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return kb


@router.delete("/{kb_id}", status_code=204)
async def delete_knowledge_base(
    kb_id: uuid.UUID,
    user: CurrentUserDep,
    db: DatabaseDep
):
    """Delete a knowledge base and all its documents."""
    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id, 
            KnowledgeBase.organization_id == user.organization_id
        )
    )
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Cascading delete handles documents and Qdrant cleanup should be called too
    # For now, we'll just delete the DB record
    await db.delete(kb)
    await db.commit()
    return None
