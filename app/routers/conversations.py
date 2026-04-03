import uuid
from typing import List, Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.dependencies import CurrentUserDep, DatabaseDep
from app.models.conversation import Conversation, Message
from app.schemas.conversation import ConversationResponse, ConversationWithMessagesResponse

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.get("")
async def list_conversations(
    user: CurrentUserDep,
    db: DatabaseDep,
    agent_id: uuid.UUID | None = None
):
    """List all conversations for the organization (admin view)."""
    query = select(Conversation).where(Conversation.organization_id == user.organization_id)
    if agent_id:
        query = query.where(Conversation.agent_id == agent_id)
        
    result = await db.execute(query.order_by(Conversation.created_at.desc()))
    convs = result.scalars().all()
    return {"success": True, "data": convs}


@router.get("/{conversation_id}")
async def get_conversation_detail(
    conversation_id: uuid.UUID,
    user: CurrentUserDep,
    db: DatabaseDep
):
    """Get full message history of a specific conversation."""
    result = await db.execute(
        select(Conversation)
        .options(joinedload(Conversation.messages))
        .where(
            Conversation.id == conversation_id, 
            Conversation.organization_id == user.organization_id
        )
    )
    conv = result.unique().scalar_one_or_none()
    
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
        
    return {"success": True, "data": conv}
