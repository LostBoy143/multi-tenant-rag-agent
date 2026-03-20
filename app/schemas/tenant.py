import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime


class TenantWithKeyResponse(BaseModel):
    tenant: TenantResponse
    api_key: str = Field(description="Shown only once at creation time. Store it securely.")


class APIKeyResponse(BaseModel):
    id: uuid.UUID
    prefix: str
    is_active: bool
    created_at: datetime
