import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from transaction.models.transaction import Category, TransactionType


# ── Requests ──────────────────────────────────────────────────────────────

class TransactionCreate(BaseModel):
    amount: Decimal = Field(gt=0, decimal_places=2)
    currency: str = Field(default="VND", pattern=r"^[A-Z]{3}$")
    type: TransactionType = TransactionType.EXPENSE
    category: Category
    note: str | None = Field(default=None, max_length=500)
    transaction_date: date


class TransactionUpdate(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    category: Category | None = None
    note: str | None = Field(default=None, max_length=500)
    transaction_date: date | None = None


# ── Responses ─────────────────────────────────────────────────────────────

class TransactionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    amount: Decimal
    currency: str
    type: TransactionType
    category: Category
    note: str | None
    transaction_date: date
    created_at: datetime

    model_config = {"from_attributes": True}


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
    total: int
    page: int
    page_size: int


# ── Internal event payload (published to RabbitMQ) ────────────────────────

class TransactionCreatedEvent(BaseModel):
    """
    Canonical event shape published to fanout exchange.
    Other services consume this — treat as a public contract.
    Changing field names = breaking change.
    """
    event_id: uuid.UUID          # idempotency key for consumers
    transaction_id: uuid.UUID
    user_id: uuid.UUID
    amount: str                  # str to avoid Decimal serialization issues across services
    currency: str
    type: str
    category: str
    note: str | None = None      # user-entered note/description for this transaction
    transaction_date: str        # ISO 8601
    occurred_at: str             # ISO 8601 — when event was emitted