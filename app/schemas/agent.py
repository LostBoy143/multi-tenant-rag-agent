import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentBase(BaseModel):
    name: str
    description: str | None = None
    system_prompt: str | None = Field(None, alias="systemPrompt")
    settings: dict[str, Any] | None = None

    class Config:
        populate_by_name = True


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = Field(None, alias="systemPrompt")
    status: str | None = None
    settings: dict[str, Any] | None = None

    class Config:
        populate_by_name = True


class AgentResponse(AgentBase):
    id: uuid.UUID
    status: str
    organization_id: uuid.UUID = Field(..., alias="orgId")
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")

    class Config:
        populate_by_name = True
