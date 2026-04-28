import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class LeadResponse(BaseModel):
    id: str
    organization_id: str
    agent_id: str | None
    conversation_id: str | None
    name: str | None
    email: str | None
    phone: str | None
    company: str | None
    location: str | None
    interest: str | None
    intent_summary: str | None
    lead_score: int
    status: str
    source_url: str | None
    metadata_json: dict | None
    captured_at: str
    updated_at: str


class LeadUpdate(BaseModel):
    status: str | None = None
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    interest: str | None = None
    notes: str | None = None  # stored inside metadata_json["notes"]


class LeadStatsResponse(BaseModel):
    total: int
    new: int
    contacted: int
    qualified: int
    converted: int
    avg_score: float | None
    leads_this_week: int
