import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, status, Header, Request
from app.core.limiter import limiter
from sqlalchemy import select

from app.dependencies import CurrentTenantDep, DatabaseDep, QdrantDep
from app.models.agent import Agent, AgentStatus
from app.models.widget import Widget
from app.models.conversation import Conversation, Message, MessageRole
from app.schemas.chat import QueryRequest, QueryResponse
from app.services.rag import answer_query

router = APIRouter(prefix="/api/v1/public", tags=["public"])


async def _get_published_agent(
    db, agent_id: uuid.UUID, org_id: uuid.UUID
) -> Agent:
    """Shared check: agent exists, belongs to org, and is published."""
    result = await db.execute(
        select(Agent).where(
            Agent.id == agent_id,
            Agent.organization_id == org_id,
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.status != AgentStatus.PUBLISHED:
        raise HTTPException(
            status_code=403,
            detail="This agent is not published yet. Please publish it from the dashboard first.",
        )
    return agent


@router.get("/widget-config")
@limiter.limit("30/minute")
async def get_widget_config(
    request: Request,
    agent_id: Annotated[uuid.UUID, Header(alias="X-Agent-ID")],
    organization: CurrentTenantDep,
    db: DatabaseDep,
):
    """Public endpoint for the embed widget to fetch its appearance config."""
    agent = await _get_published_agent(db, agent_id, organization.id)

    result = await db.execute(select(Widget).where(Widget.agent_id == agent.id))
    widget = result.scalar_one_or_none()

    theme = (widget.theme if widget and widget.theme else {}) or {}

    return {
        "success": True,
        "data": {
            "agent_name": agent.name,
            "brand_color": widget.brand_color if widget else "#f43f5e",
            "greeting": widget.greeting if widget else "Hi! How can I help you today?",
            "position": widget.position if widget else "bottom-right",
            "avatar_url": widget.avatar_url if widget else None,
            # Launcher customization
            "launcher_icon": theme.get("launcher_icon", "chat"),
            "launcher_text": theme.get("launcher_text", ""),
            "launcher_shape": theme.get("launcher_shape", "circle"),
            "tooltip_text": theme.get("tooltip_text", ""),
            "chat_height": theme.get("chat_height", 520),
            # v4 — Modern features (all optional, off by default)
            "teaser_text": theme.get("teaser_text", ""),
            "glass_effect": theme.get("glass_effect", False),
            "gradient_enabled": theme.get("gradient_enabled", False),
            "attention_dot": theme.get("attention_dot", False),
            "entrance_animation": theme.get("entrance_animation", "none"),
            "suggested_replies": theme.get("suggested_replies", []),
        },
    }


@router.post("/chat/session", status_code=201)
@limiter.limit("5/minute")
async def start_session(
    request: Request,
    agent_id: Annotated[uuid.UUID, Header(alias="X-Agent-ID")],
    organization: CurrentTenantDep,
    db: DatabaseDep,
):
    """Initialize a new chat session for a website visitor."""
    await _get_published_agent(db, agent_id, organization.id)

    conv = Conversation(organization_id=organization.id, agent_id=agent_id)
    db.add(conv)
    await db.commit()
    await db.refresh(conv)

    return {"success": True, "data": {"id": str(conv.id)}}


@router.post("/chat/query")
@limiter.limit("10/minute")
async def public_query(
    request: Request,
    body: QueryRequest,
    organization: CurrentTenantDep,
    db: DatabaseDep,
    qdrant: QdrantDep,
    conversation_id: Annotated[uuid.UUID | None, Header(alias="X-Conversation-ID")] = None,
):
    """Public RAG chat endpoint for website visitors."""
    await _get_published_agent(db, body.agent_id, organization.id)

    try:
        response = await answer_query(
            qdrant=qdrant,
            organization_id=organization.id,
            agent_id=body.agent_id,
            question=body.question,
            top_k=body.top_k,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if conversation_id:
        conv_result = await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.organization_id == organization.id,
            )
        )
        conv = conv_result.scalar_one_or_none()

        if conv:
            user_msg = Message(
                conversation_id=conversation_id,
                role=MessageRole.USER,
                content=body.question,
            )
            assistant_msg = Message(
                conversation_id=conversation_id,
                role=MessageRole.ASSISTANT,
                content=response.answer,
                sources=[s.model_dump() for s in response.sources],
                response_time_ms=response.response_time_ms,
            )
            db.add_all([user_msg, assistant_msg])
            await db.commit()

    return {"success": True, "data": {"answer": response.answer, "sources": [s.model_dump() for s in response.sources]}}

from pydantic import BaseModel, EmailStr
class LeadRequest(BaseModel):
    name: str
    email: EmailStr
    company: str
    requirements: str

@router.post("/lead", status_code=201)
@limiter.limit("5/minute")
async def capture_lead(
    request: Request,
    body: LeadRequest,
):
    """Capture leads from the marketing landing page."""
    from app.core.email import send_lead_email
    await send_lead_email(
        name=body.name,
        email=body.email,
        company=body.company,
        requirements=body.requirements
    )
    return {"success": True, "message": "Lead captured successfully"}
