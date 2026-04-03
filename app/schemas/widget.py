import uuid
from pydantic import BaseModel, Field


class WidgetBase(BaseModel):
    theme: dict | None = None
    position: str = "bottom-right"
    greeting: str | None = None
    brand_color: str | None = Field(None, alias="brandColor")
    avatar_url: str | None = Field(None, alias="avatarUrl")

    class Config:
        populate_by_name = True


class WidgetUpdate(WidgetBase):
    pass


class WidgetResponse(WidgetBase):
    id: uuid.UUID
    agent_id: uuid.UUID = Field(..., alias="agentId")

    class Config:
        populate_by_name = True
