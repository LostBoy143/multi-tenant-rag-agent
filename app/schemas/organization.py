from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class OrganizationCreate(BaseModel):
    name: str
    slug: str


class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    plan: str
    created_at: datetime


class OrganizationWithKeyResponse(BaseModel):
    organization: OrganizationResponse
    api_key: str
