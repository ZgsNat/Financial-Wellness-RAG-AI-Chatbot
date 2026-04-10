import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from transaction.database import Base


class TransactionType(StrEnum):
    EXPENSE = "expense"
    INCOME = "income"


class Category(StrEnum):
    """
    Fixed taxonomy — keeps AI analysis consistent.
    New categories require a migration + model update intentionally.
    """
    FOOD = "food"
    SHOPPING = "shopping"
    ENTERTAINMENT = "entertainment"
    TRANSPORT = "transport"
    HEALTH = "health"
    EDUCATION = "education"
    UTILITIES = "utilities"
    OTHER = "other"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Injected by Kong from JWT — this service never receives or validates JWTs directly
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="VND")
    type: Mapped[TransactionType] = mapped_column(
        String(10), nullable=False, default=TransactionType.EXPENSE
    )
    category: Mapped[Category] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Date of the transaction (user-supplied, can differ from created_at)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
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
        # Common query: user's transactions in a date range
        Index("ix_transactions_user_date", "user_id", "transaction_date"),
    )