"""
Insight model stores the result of AI analysis triggered by transaction/journal events.

One insight record per (user_id, insight_type, period).
When a new transaction arrives, we upsert — not append — to avoid unbounded growth.
The `source_event_id` tracks which event triggered the last update (for debugging).
"""
import uuid
from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from insight.database import Base


class InsightType(StrEnum):
    SPENDING_PATTERN = "spending_pattern"      # "You spend 60% on shopping when stressed"
    MOOD_SPENDING_CORRELATION = "mood_spending" # "Shopping spikes on low-mood days"
    BUDGET_SUMMARY = "budget_summary"           # "This month: 2.4M VND spent"
    WELLNESS_SUGGESTION = "wellness_suggestion" # "Try a walk instead of shopping when stressed"


class Insight(Base):
    __tablename__ = "insights"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    insight_type: Mapped[InsightType] = mapped_column(String(30), nullable=False)

    # Human-readable summary — shown directly in UI
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # Full structured analysis — used by frontend for richer display
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Which event last triggered this insight's regeneration
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        # One active insight per type per user — upsert target
        UniqueConstraint("user_id", "insight_type", name="uq_insight_user_type"),
        Index("ix_insights_user_id", "user_id"),
    )