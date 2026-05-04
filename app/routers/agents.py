import uuid
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.dependencies import CurrentUserDep, DatabaseDep
from app.models.agent import Agent, AgentStatus
from app.schemas.agent import AgentCreate, AgentUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


def _serialize_agent(agent: Agent) -> dict[str, Any]:
    return {
        "id": str(agent.id),
        "name": agent.name,
        "description": agent.description,
        "system_prompt": agent.system_prompt,
        "status": agent.status,
        "settings": agent.settings,
        "organization_id": str(agent.organization_id),
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
    }


@router.get("")
async def list_agents(
    user: CurrentUserDep,
    db: DatabaseDep
):
    """List all agents for the current organization."""
    result = await db.execute(
        select(Agent)
        .where(Agent.organization_id == user.organization_id)
        .order_by(Agent.created_at.desc())
    )
    agents = result.scalars().all()
    return {"success": True, "data": [_serialize_agent(a) for a in agents]}


@router.post("", status_code=201)
async def create_agent(
    body: AgentCreate,
    user: CurrentUserDep,
    db: DatabaseDep
):
    """Create a new agent for the organization (one per org rule)."""
    # 1. Enforce one agent per organization constraint
    existing_result = await db.execute(
        select(Agent).where(Agent.organization_id == user.organization_id)
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Organization already has an active agent. Only one agent is allowed per organization."
        )

    agent = Agent(
        name=body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        settings=body.settings,
        organization_id=user.organization_id,
        status=AgentStatus.DRAFT
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return {"success": True, "data": _serialize_agent(agent)}


@router.get("/{agent_id}")
async def get_agent(
    agent_id: uuid.UUID,
    user: CurrentUserDep,
    db: DatabaseDep
):
    """Get details of a specific agent."""
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.organization_id == user.organization_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"success": True, "data": _serialize_agent(agent)}


@router.patch("/{agent_id}")
async def update_agent(
    agent_id: uuid.UUID,
    body: AgentUpdate,
    user: CurrentUserDep,
    db: DatabaseDep
):
    """Update a specific agent."""
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.organization_id == user.organization_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(agent, key, value)

    await db.commit()
    await db.refresh(agent)
    return {"success": True, "data": _serialize_agent(agent)}


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: uuid.UUID,
    user: CurrentUserDep,
    db: DatabaseDep
):
    """Delete a specific agent."""
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.organization_id == user.organization_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    await db.delete(agent)
    await db.commit()
    return None


@router.post("/{agent_id}/publish")
async def publish_agent(
    agent_id: uuid.UUID,
    user: CurrentUserDep,
    db: DatabaseDep
):
    """Mark an agent as published."""
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.organization_id == user.organization_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent.status = AgentStatus.PUBLISHED
    await db.commit()
    await db.refresh(agent)
    return {"success": True, "data": _serialize_agent(agent)}


class PreviewRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


@router.post("/{agent_id}/preview")
async def preview_agent_chat(
    agent_id: uuid.UUID,
    body: PreviewRequest,
    user: CurrentUserDep,
    db: DatabaseDep,
):
    """
    Dashboard-only preview endpoint.
    Uses JWT auth so the logged-in user can test their bot
    without needing an API key.
    """
    from app.dependencies import get_qdrant
    from app.services.rag import LLMProviderError, answer_query

    # Verify agent belongs to user's organization
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.organization_id == user.organization_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    qdrant = await get_qdrant()
    try:
        response, _ = await answer_query(
            qdrant=qdrant,
            organization_id=user.organization_id,
            agent_id=agent_id,
            question=body.question,
            top_k=body.top_k,
        )
        return {"success": True, "data": {"answer": response.answer, "sources": [s.model_dump() for s in response.sources]}}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except LLMProviderError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI provider is temporarily unavailable. Please try again shortly.",
        ) from e


# ──────────────────────────────────────────────
# Knowledge Base Linking
# ──────────────────────────────────────────────

class LinkKBRequest(BaseModel):
    knowledge_base_id: uuid.UUID


@router.get("/{agent_id}/knowledge-bases")
async def list_agent_kbs(
    agent_id: uuid.UUID,
    user: CurrentUserDep,
    db: DatabaseDep,
):
    """List all knowledge bases linked to this agent."""
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(Agent)
        .options(selectinload(Agent.knowledge_bases))
        .where(Agent.id == agent_id, Agent.organization_id == user.organization_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"success": True, "data": [{"id": str(kb.id), "name": kb.name} for kb in agent.knowledge_bases]}


@router.post("/{agent_id}/knowledge-bases", status_code=201)
async def link_kb_to_agent(
    agent_id: uuid.UUID,
    body: LinkKBRequest,
    user: CurrentUserDep,
    db: DatabaseDep,
):
    """Link a knowledge base to this agent."""
    from app.models.agent import AgentKnowledgeBase
    from app.models.knowledge_base import KnowledgeBase

    # Verify agent
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.organization_id == user.organization_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Agent not found")

    # Verify KB belongs to same org
    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == body.knowledge_base_id,
            KnowledgeBase.organization_id == user.organization_id
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Check if already linked
    result = await db.execute(
        select(AgentKnowledgeBase).where(
            AgentKnowledgeBase.agent_id == agent_id,
            AgentKnowledgeBase.knowledge_base_id == body.knowledge_base_id
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Knowledge base already linked")

    link = AgentKnowledgeBase(agent_id=agent_id, knowledge_base_id=body.knowledge_base_id)
    db.add(link)
    await db.commit()
    return {"success": True, "message": "Knowledge base linked"}


@router.delete("/{agent_id}/knowledge-bases/{kb_id}", status_code=204)
async def unlink_kb_from_agent(
    agent_id: uuid.UUID,
    kb_id: uuid.UUID,
    user: CurrentUserDep,
    db: DatabaseDep,
):
    """Unlink a knowledge base from this agent."""
    from app.models.agent import AgentKnowledgeBase

    # Verify agent ownership
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.organization_id == user.organization_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Agent not found")

    result = await db.execute(
        select(AgentKnowledgeBase).where(
            AgentKnowledgeBase.agent_id == agent_id,
            AgentKnowledgeBase.knowledge_base_id == kb_id
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    await db.delete(link)
    await db.commit()
    return None
