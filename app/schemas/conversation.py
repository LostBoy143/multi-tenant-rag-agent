import uuid
from datetime import datetime
from typing import Any, List
from pydantic import BaseModel, Field


class MessageBase(BaseModel):
    role: str
    content: str
    sources: dict | None = None


class MessageResponse(MessageBase):
    id: uuid.UUID
    created_at: datetime = Field(..., alias="createdAt")

    class Config:
        populate_by_name = True


class ConversationBase(BaseModel):
    agent_id: uuid.UUID | None = Field(None, alias="agentId")
    visitor_id: str | None = Field(None, alias="visitorId")
    metadata_json: dict[str, Any] | None = Field(None, alias="metadata")

    class Config:
        populate_by_name = True


class ConversationResponse(ConversationBase):
    id: uuid.UUID
    organization_id: uuid.UUID = Field(..., alias="orgId")
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")

    class Config:
        populate_by_name = True


class ConversationWithMessagesResponse(ConversationResponse):
    messages: List[MessageResponse] = []
