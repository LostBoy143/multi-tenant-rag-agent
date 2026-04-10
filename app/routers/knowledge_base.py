import uuid
from typing import Any, List, Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func as sa_func, select
from sqlalchemy.orm import selectinload

from app.dependencies import CurrentUserDep, DatabaseDep
from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document
from app.schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseResponse

router = APIRouter(prefix="/api/v1/knowledge-bases", tags=["knowledge-bases"])


def _serialize_kb(kb: KnowledgeBase, doc_count: int | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": str(kb.id),
        "name": kb.name,
        "description": kb.description,
        "organization_id": str(kb.organization_id),
        "created_at": kb.created_at.isoformat() if kb.created_at else None,
        "updated_at": kb.updated_at.isoformat() if kb.updated_at else None,
    }
    if doc_count is not None:
        data["doc_count"] = doc_count
    return data


@router.get("")
async def list_knowledge_bases(
    user: CurrentUserDep,
    db: DatabaseDep
):
    """List all knowledge bases for the current organization, with document counts."""
    result = await db.execute(
        select(KnowledgeBase)
        .where(KnowledgeBase.organization_id == user.organization_id)
        .order_by(KnowledgeBase.created_at.desc())
    )
    kbs = result.scalars().all()

    count_result = await db.execute(
        select(Document.knowledge_base_id, sa_func.count(Document.id))
        .where(Document.knowledge_base_id.in_([kb.id for kb in kbs]))
        .group_by(Document.knowledge_base_id)
    )
    counts: dict[uuid.UUID, int] = {row[0]: row[1] for row in count_result.all()}

    return {
        "success": True,
        "data": [_serialize_kb(kb, counts.get(kb.id, 0)) for kb in kbs],
    }


@router.post("", status_code=201)
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
    return {"success": True, "data": _serialize_kb(kb, 0)}


@router.get("/{kb_id}")
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
    return {"success": True, "data": _serialize_kb(kb)}


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

    await db.delete(kb)
    await db.commit()
    return None
