import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.dependencies import CurrentUserDep, DatabaseDep
from app.models.conversation import Conversation, Message

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


def _serialize_message(msg: Message) -> dict:
    return {
        "id": str(msg.id),
        "role": msg.role,
        "content": msg.content,
        "sources": msg.sources,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


def _serialize_conversation(conv: Conversation, *, include_messages: bool = False) -> dict:
    last_msg = None
    if conv.messages:
        sorted_msgs = sorted(conv.messages, key=lambda m: m.created_at)
        last_msg = sorted_msgs[-1].content[:100] if sorted_msgs else None

    data: dict = {
        "id": str(conv.id),
        "agent_id": str(conv.agent_id) if conv.agent_id else None,
        "visitor_id": conv.visitor_id,
        "metadata": conv.metadata_json,
        "message_count": len(conv.messages) if conv.messages else 0,
        "last_message": last_msg,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
    }
    if include_messages:
        data["messages"] = [_serialize_message(m) for m in sorted(conv.messages, key=lambda m: m.created_at)]
    return data


@router.get("")
async def list_conversations(
    user: CurrentUserDep,
    db: DatabaseDep,
    agent_id: uuid.UUID | None = None,
):
    """List all conversations for the organization."""
    query = (
        select(Conversation)
        .options(joinedload(Conversation.messages))
        .where(Conversation.organization_id == user.organization_id)
    )
    if agent_id:
        query = query.where(Conversation.agent_id == agent_id)

    result = await db.execute(query.order_by(Conversation.created_at.desc()))
    convs = result.unique().scalars().all()
    return {"success": True, "data": [_serialize_conversation(c) for c in convs]}


@router.get("/{conversation_id}")
async def get_conversation_detail(
    conversation_id: uuid.UUID,
    user: CurrentUserDep,
    db: DatabaseDep,
):
    """Get full message history of a specific conversation."""
    result = await db.execute(
        select(Conversation)
        .options(joinedload(Conversation.messages))
        .where(
            Conversation.id == conversation_id,
            Conversation.organization_id == user.organization_id,
        )
    )
    conv = result.unique().scalar_one_or_none()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {"success": True, "data": _serialize_conversation(conv, include_messages=True)}
