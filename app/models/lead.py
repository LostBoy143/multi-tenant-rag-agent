import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LeadStatus(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    CONVERTED = "converted"
    LOST = "lost"
    ARCHIVED = "archived"


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Contact details (anti-hallucination: only store what user actually wrote)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    company: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)  # v1: null; v2: geo

    # Intent signals
    interest: Mapped[str | None] = mapped_column(String(100), nullable=True)  # e.g. "Pricing", "Demo"
    intent_summary: Mapped[str | None] = mapped_column(Text, nullable=True)   # v2: async LLM

    # Scoring & status
    lead_score: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default=LeadStatus.NEW, index=True)

    # Long-term memory: persistent browser visitor tracking
    visitor_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Attribution
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Debug / extensibility
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # One lead row per conversation (upsert key)
    __table_args__ = (
        UniqueConstraint("conversation_id", name="uq_leads_conversation_id"),
    )
