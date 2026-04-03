import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from app.core.limiter import limiter
from sqlalchemy import select

from app.dependencies import CurrentTenantDep, DatabaseDep, QdrantDep
from app.models.agent import Agent
from app.models.conversation import Conversation, Message, MessageRole
from app.schemas.chat import QueryRequest, QueryResponse
from app.services.rag import answer_query

router = APIRouter(prefix="/api/v1/public", tags=["public"])


@router.post("/chat/session", status_code=201)
@limiter.limit("5/minute")
async def start_session(
    request: Request,
    agent_id: Annotated[uuid.UUID, Header(alias="X-Agent-ID")],
    organization: CurrentTenantDep,
    db: DatabaseDep
):
    """
    Initialize a new chat session for a website visitor.
    Requires a valid API Key and Agent ID.
    Returns the session_id (conversation_id).
    """
    # 1. Verify agent belongs to organization
    agent_result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.organization_id == organization.id)
    )
    if not agent_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Agent not found")

    # 2. Create conversation
    conv = Conversation(
        organization_id=organization.id,
        agent_id=agent_id
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    
    return {"id": conv.id}


@router.post("/chat/query", response_model=QueryResponse)
@limiter.limit("10/minute")
async def public_query(
    request: Request,
    body: QueryRequest,
    organization: CurrentTenantDep,
    db: DatabaseDep,
    qdrant: QdrantDep,
    conversation_id: Annotated[uuid.UUID | None, Header(alias="X-Conversation-ID")] = None
):
    """
    Public RAG chat endpoint for website visitors.
    Directly answers questions and saves them to history if a Conversation ID is provided.
    """
    # 1. Answer via RAG
    # Note: We use body.agent_id from the query request
    try:
        response = await answer_query(
            qdrant=qdrant,
            organization_id=organization.id,
            agent_id=body.agent_id,
            question=body.question,
            top_k=body.top_k
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # 2. Save history if conversation_id is provided
    if conversation_id:
        # Check if conversation exists and belongs to this organization
        conv_result = await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id, 
                Conversation.organization_id == organization.id
            )
        )
        conv = conv_result.scalar_one_or_none()
        
        if conv:
            # Save user message
            user_msg = Message(
                conversation_id=conversation_id,
                role=MessageRole.USER,
                content=body.question
            )
            # Save assistant message
            assistant_msg = Message(
                conversation_id=conversation_id,
                role=MessageRole.ASSISTANT,
                content=response.answer,
                sources=[s.model_dump() for s in response.sources]
            )
            db.add_all([user_msg, assistant_msg])
            await db.commit()

    return response
