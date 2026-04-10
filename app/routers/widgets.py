import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.dependencies import CurrentUserDep, DatabaseDep
from app.models.agent import Agent
from app.models.widget import Widget
from app.schemas.widget import WidgetResponse, WidgetUpdate

router = APIRouter(prefix="/api/v1/widgets", tags=["widgets"])


@router.get("/{agent_id}")
async def get_agent_widget(
    agent_id: uuid.UUID,
    user: CurrentUserDep,
    db: DatabaseDep
):
    """Get the widget configuration for a specific agent."""
    # Ensure agent belongs to organization
    agent_result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.organization_id == user.organization_id)
    )
    if not agent_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Agent not found")

    result = await db.execute(select(Widget).where(Widget.agent_id == agent_id))
    widget = result.scalar_one_or_none()
    
    if not widget:
        # Create default widget if it doesn't exist
        widget = Widget(agent_id=agent_id)
        db.add(widget)
        await db.commit()
        await db.refresh(widget)
        
    return {"success": True, "data": _serialize_widget(widget)}


@router.patch("/{agent_id}")
async def update_agent_widget(
    agent_id: uuid.UUID,
    body: WidgetUpdate,
    user: CurrentUserDep,
    db: DatabaseDep
):
    """Update widget appearance and settings."""
    agent_result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.organization_id == user.organization_id)
    )
    if not agent_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Agent not found")

    result = await db.execute(select(Widget).where(Widget.agent_id == agent_id))
    widget = result.scalar_one_or_none()
    
    if not widget:
        widget = Widget(agent_id=agent_id)
        db.add(widget)

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(widget, key, value)

    await db.commit()
    await db.refresh(widget)
    return {"success": True, "data": _serialize_widget(widget)}


def _serialize_widget(widget: Widget) -> dict:
    return {
        "id": str(widget.id),
        "agent_id": str(widget.agent_id),
        "brand_color": widget.brand_color,
        "greeting": widget.greeting,
        "position": widget.position,
        "avatar_url": widget.avatar_url,
        "theme": widget.theme,
    }
