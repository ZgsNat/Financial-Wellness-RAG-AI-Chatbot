"""
Alert model — a persisted notification shown in the frontend.

Phase 1: rule-based alerts (spending threshold exceeded, high-frequency shopping on low mood).
Phase 2: AI-generated alerts from insight-service recommendations.

Design decision: alerts are immutable once created.
Marking as "read" updates is_read only — never deletes.
This gives the frontend a clean unread count and preserves history.
"""
import uuid
from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from notification.database import Base


class AlertType(StrEnum):
    SPENDING_SPIKE = "spending_spike"         # single transaction unusually large
    CATEGORY_OVERLOAD = "category_overload"   # category dominates this week
    MOOD_SPENDING_WARNING = "mood_spending_warning"  # bought expensive stuff on bad mood day
    BUDGET_EXCEEDED = "budget_exceeded"       # phase 2: user set budget goal
    WELLNESS_TIP = "wellness_tip"             # positive suggestion


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    alert_type: Mapped[AlertType] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Which event triggered this alert — for traceability
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )