import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from journal.models.journal import MoodScore


# ── Mood ──────────────────────────────────────────────────────────────────

class MoodEntryCreate(BaseModel):
    score: MoodScore
    note: str | None = Field(default=None, max_length=300)


class MoodEntryResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    score: int
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Journal ───────────────────────────────────────────────────────────────

class JournalEntryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10_000)


class JournalEntryUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=10_000)


class JournalEntryResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    content: str
    word_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JournalEntryListResponse(BaseModel):
    items: list[JournalEntryResponse]
    total: int
    page: int
    page_size: int


# ── Events ────────────────────────────────────────────────────────────────

class JournalEntryCreatedEvent(BaseModel):
    """
    Published when a journal entry or mood is created.
    insight-service uses this to trigger RAG re-indexing of the user's journal.
    """
    event_id: uuid.UUID
    entry_type: str          # "journal" | "mood"
    entry_id: uuid.UUID
    user_id: uuid.UUID
    occurred_at: str
    # Denormalized payload fields for RAG ingestion (avoids service-to-service HTTP call)
    content: str | None = None    # journal entry text
    score: int | None = None      # mood score 1-5
    note: str | None = None       # optional mood note
    created_at: str | None = None # ISO timestamp used for date header in embeddings