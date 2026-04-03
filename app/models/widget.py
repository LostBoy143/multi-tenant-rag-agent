import uuid
from sqlalchemy import ForeignKey, String, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Widget(Base):
    __tablename__ = "widgets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), unique=True)
    
    theme: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    position: Mapped[str] = mapped_column(String(50), default="bottom-right")
    greeting: Mapped[str | None] = mapped_column(String(500), nullable=True)
    brand_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    agent: Mapped["Agent"] = relationship(back_populates="widget")
