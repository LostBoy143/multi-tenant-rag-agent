from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import select, func, and_, case, cast, Integer, Numeric

from app.dependencies import CurrentUserDep, DatabaseDep
from app.models.conversation import Conversation, Message, MessageRole
from app.models.agent import Agent, AgentStatus
from app.models.document import Document

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/overview")
async def get_overview(user: CurrentUserDep, db: DatabaseDep):
    org_id = user.organization_id
    now = datetime.now(timezone.utc)

    total_conversations_q = select(func.count(Conversation.id)).where(
        Conversation.organization_id == org_id
    )

    total_messages_q = (
        select(func.count(Message.id))
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.organization_id == org_id)
    )

    # Conversations that have at least one message in the last 24 hours
    cutoff_24h = now - timedelta(hours=24)
    active_24h_q = (
        select(func.count(func.distinct(Conversation.id)))
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            and_(
                Conversation.organization_id == org_id,
                Message.created_at >= cutoff_24h,
            )
        )
    )

    active_chatbots_q = select(func.count(Agent.id)).where(
        and_(
            Agent.organization_id == org_id,
            Agent.status == AgentStatus.PUBLISHED,
        )
    )

    total_documents_q = select(func.count(Document.id)).where(
        Document.organization_id == org_id
    )

    total_chunks_q = select(func.coalesce(func.sum(Document.chunk_count), 0)).where(
        Document.organization_id == org_id
    )

    avg_messages_q = (
        select(
            func.round(
                cast(func.count(Message.id), Numeric)
                / func.nullif(cast(func.count(func.distinct(Message.conversation_id)), Numeric), 0),
                1,
            )
        )
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.organization_id == org_id)
    )

    avg_response_time_q = (
        select(func.avg(Message.response_time_ms))
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            and_(
                Conversation.organization_id == org_id,
                Message.role == MessageRole.ASSISTANT,
                Message.response_time_ms.isnot(None),
            )
        )
    )

    # Trend: last 30 days vs previous 30 days
    cutoff_30d = now - timedelta(days=30)
    cutoff_60d = now - timedelta(days=60)

    convs_last_30_q = select(func.count(Conversation.id)).where(
        and_(
            Conversation.organization_id == org_id,
            Conversation.created_at >= cutoff_30d,
        )
    )
    convs_prev_30_q = select(func.count(Conversation.id)).where(
        and_(
            Conversation.organization_id == org_id,
            Conversation.created_at >= cutoff_60d,
            Conversation.created_at < cutoff_30d,
        )
    )

    msgs_last_30_q = (
        select(func.count(Message.id))
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            and_(
                Conversation.organization_id == org_id,
                Message.created_at >= cutoff_30d,
            )
        )
    )
    msgs_prev_30_q = (
        select(func.count(Message.id))
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            and_(
                Conversation.organization_id == org_id,
                Message.created_at >= cutoff_60d,
                Message.created_at < cutoff_30d,
            )
        )
    )

    total_conversations = (await db.execute(total_conversations_q)).scalar()
    total_messages = (await db.execute(total_messages_q)).scalar()
    active_conversations_24h = (await db.execute(active_24h_q)).scalar()
    active_chatbots = (await db.execute(active_chatbots_q)).scalar()
    total_documents = (await db.execute(total_documents_q)).scalar()
    total_chunks = (await db.execute(total_chunks_q)).scalar()
    avg_messages_per_conversation = (await db.execute(avg_messages_q)).scalar()
    avg_response_time_ms = (await db.execute(avg_response_time_q)).scalar()
    convs_last_30 = (await db.execute(convs_last_30_q)).scalar()
    convs_prev_30 = (await db.execute(convs_prev_30_q)).scalar()
    msgs_last_30 = (await db.execute(msgs_last_30_q)).scalar()
    msgs_prev_30 = (await db.execute(msgs_prev_30_q)).scalar()

    def pct_change(current: int, previous: int) -> float | None:
        if not previous:
            return None
        return round((current - previous) / previous * 100, 1)

    return {
        "success": True,
        "data": {
            "total_conversations": total_conversations,
            "total_messages": total_messages,
            "active_conversations_24h": active_conversations_24h,
            "active_chatbots": active_chatbots,
            "total_documents": total_documents,
            "total_chunks": total_chunks,
            "avg_messages_per_conversation": avg_messages_per_conversation or 0.0,
            "avg_response_time_ms": (
                round(avg_response_time_ms, 1) if avg_response_time_ms is not None else None
            ),
            "conversations_trend_pct": pct_change(convs_last_30, convs_prev_30),
            "messages_trend_pct": pct_change(msgs_last_30, msgs_prev_30),
        },
    }


@router.get("/trends")
async def get_trends(
    user: CurrentUserDep,
    db: DatabaseDep,
    period: str = Query(default="day"),
    days: int = Query(default=30),
):
    org_id = user.organization_id
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    date_trunc = func.date_trunc("day", Message.created_at).label("date")

    q = (
        select(
            date_trunc,
            func.count(func.distinct(Message.conversation_id)).label("conversations"),
            func.count(Message.id).label("messages"),
            func.sum(case((Message.role == MessageRole.USER, 1), else_=0)).label("user_messages"),
            func.sum(case((Message.role == MessageRole.ASSISTANT, 1), else_=0)).label("bot_messages"),
        )
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            and_(
                Conversation.organization_id == org_id,
                Message.created_at >= cutoff,
            )
        )
        .group_by(date_trunc)
        .order_by(date_trunc)
    )

    result = await db.execute(q)
    rows = result.all()

    data = [
        {
            "date": row.date.date().isoformat() if row.date else None,
            "conversations": row.conversations,
            "messages": row.messages,
            "user_messages": row.user_messages,
            "bot_messages": row.bot_messages,
        }
        for row in rows
    ]

    return {
        "success": True,
        "data": {
            "period": period,
            "data": data,
        },
    }


@router.get("/heatmap")
async def get_heatmap(
    user: CurrentUserDep,
    db: DatabaseDep,
    days: int = Query(default=30),
):
    org_id = user.organization_id
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    dow = cast(func.extract("dow", Message.created_at), Integer).label("day")
    hour = cast(func.extract("hour", Message.created_at), Integer).label("hour")

    q = (
        select(
            dow,
            hour,
            func.count(Message.id).label("count"),
        )
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            and_(
                Conversation.organization_id == org_id,
                Message.created_at >= cutoff,
            )
        )
        .group_by(dow, hour)
        .order_by(dow, hour)
    )

    result = await db.execute(q)
    rows = result.all()

    data = [{"day": row.day, "hour": row.hour, "count": row.count} for row in rows]
    max_count = max((row.count for row in rows), default=0)

    return {
        "success": True,
        "data": {
            "data": data,
            "max_count": max_count,
        },
    }
