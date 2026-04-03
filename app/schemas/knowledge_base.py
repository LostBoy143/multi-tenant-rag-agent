import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class KnowledgeBaseBase(BaseModel):
    name: str


class KnowledgeBaseCreate(KnowledgeBaseBase):
    pass


class KnowledgeBaseResponse(KnowledgeBaseBase):
    id: uuid.UUID
    organization_id: uuid.UUID = Field(..., alias="orgId")
    created_at: datetime = Field(..., alias="createdAt")

    class Config:
        populate_by_name = True
