import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class APIKeyBase(BaseModel):
    name: str


class APIKeyCreate(APIKeyBase):
    pass


class APIKeyResponse(APIKeyBase):
    id: uuid.UUID
    prefix: str
    is_active: bool = Field(..., alias="isActive")
    created_at: datetime = Field(..., alias="createdAt")
    last_used_at: datetime | None = Field(None, alias="lastUsedAt")

    class Config:
        populate_by_name = True


class APIKeySecretResponse(APIKeyResponse):
    key: str # Full plain-text key (only on creation)
