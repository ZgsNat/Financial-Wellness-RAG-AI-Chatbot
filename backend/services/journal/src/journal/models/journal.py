"""
Journal service owns two related concepts:
  - MoodEntry: a timestamped mood score + optional note (quick daily check-in)
  - JournalEntry: a longer personal note the user writes about their day/feelings

Both are inputs to the insight-service RAG pipeline later.
Keeping them separate lets the AI distinguish
"I felt stressed" (mood signal) from "I bought a model kit to cope" (journal context).
"""
import uuid
from datetime import datetime, timezone
from enum import IntEnum

from sqlalchemy import DateTime, Integer, SmallInteger, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from journal.database import Base


class MoodScore(IntEnum):
    """1-5 scale. Intentionally simple — avoids analysis paralysis for the user."""
    VERY_BAD = 1
    BAD = 2
    NEUTRAL = 3
    GOOD = 4
    VERY_GOOD = 5


class MoodEntry(Base):
    __tablename__ = "mood_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)   # 1-5
    note: Mapped[str | None] = mapped_column(Text, nullable=True)      # "why do I feel this way"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # word_count cached to avoid re-scanning on list queries
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )