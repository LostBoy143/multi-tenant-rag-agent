import uuid
import logging
from typing import List, Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.auth.schemas import UserInToken
from app.dependencies import CurrentUserDep, DatabaseDep
from app.models.agent import Agent, AgentStatus
from app.schemas.agent import AgentCreate, AgentResponse, AgentUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


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
    return {"success": True, "data": agents}


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
    return {"success": True, "data": agent}


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
    return {"success": True, "data": agent}


@router.patch("/{agent_id}", response_model=AgentResponse)
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

    update_data = body.model_dump(exclude_unset=True, by_alias=True)
    for key, value in update_data.items():
        setattr(agent, key, value)

    await db.commit()
    await db.refresh(agent)
    return agent


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


@router.post("/{agent_id}/publish", response_model=AgentResponse)
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
    return agent
