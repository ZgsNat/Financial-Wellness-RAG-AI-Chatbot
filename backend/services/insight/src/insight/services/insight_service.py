"""
InsightService — orchestrates AI analysis and persists results.

Phase 1 (now): generates deterministic rule-based insights.
  Rationale: gets the full pipeline working (event → consumer → DB → API → UI)
  without LLM latency or API cost during development.

Phase 2: swap _generate_spending_summary() with LLM call.
  The interface doesn't change — only the implementation of the _generate_* methods.
  This is why the service layer exists: consumers don't call LLM directly.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from insight.models.insight import Insight, InsightType


class InsightService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_insights_for_user(self, user_id: uuid.UUID) -> list[Insight]:
        result = await self._db.execute(
            select(Insight)
            .where(Insight.user_id == user_id)
            .order_by(Insight.updated_at.desc())
        )
        return list(result.scalars().all())

    async def refresh_spending_insight(
        self,
        user_id: str,
        source_event_id: str | None,
        transaction_payload: dict,
    ) -> None:
        """
        Upsert spending pattern insight.
        Phase 1: rule-based summary from the event payload itself.
        Phase 2: fetch user's transaction history, pass to LLM.
        """
        summary = self._generate_spending_summary(transaction_payload)

        await self._upsert_insight(
            user_id=uuid.UUID(user_id),
            insight_type=InsightType.SPENDING_PATTERN,
            summary=summary,
            source_event_id=uuid.UUID(source_event_id) if source_event_id else None,
        )

    async def refresh_mood_insight(
        self,
        user_id: str,
        source_event_id: str | None,
        entry_type: str | None,
    ) -> None:
        """
        Upsert mood-spending correlation insight.
        Phase 1: placeholder text acknowledging the entry.
        Phase 2: fetch mood history + transaction history, correlate via LLM.
        """
        summary = (
            "Your mood data is being analyzed. Check back after a few more entries."
            if entry_type == "mood"
            else "Your journal entry has been recorded and will inform future insights."
        )

        await self._upsert_insight(
            user_id=uuid.UUID(user_id),
            insight_type=InsightType.MOOD_SPENDING_CORRELATION,
            summary=summary,
            source_event_id=uuid.UUID(source_event_id) if source_event_id else None,
        )

    async def _upsert_insight(
        self,
        user_id: uuid.UUID,
        insight_type: InsightType,
        summary: str,
        source_event_id: uuid.UUID | None = None,
        detail: str | None = None,
    ) -> None:
        """
        PostgreSQL upsert on (user_id, insight_type).
        One active insight per type per user — always reflects latest analysis.
        """
        stmt = (
            pg_insert(Insight)
            .values(
                id=uuid.uuid4(),
                user_id=user_id,
                insight_type=insight_type,
                summary=summary,
                detail=detail,
                source_event_id=source_event_id,
                generated_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            .on_conflict_do_update(
                constraint="uq_insight_user_type",
                set_={
                    "summary": summary,
                    "detail": detail,
                    "source_event_id": source_event_id,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
        )
        await self._db.execute(stmt)
        await self._db.commit()

    # ── Phase 1 stub generators ───────────────────────────────────────────

    def _generate_spending_summary(self, payload: dict) -> str:
        """
        Rule-based summary from a single transaction event.
        Replaced by LLM call in phase 2 that receives full transaction history.
        """
        category = payload.get("category", "unknown")
        amount = payload.get("amount", "0")
        currency = payload.get("currency", "VND")
        try:
            formatted = f"{Decimal(amount):,.0f}"
        except Exception:
            formatted = amount
        return f"Latest transaction: {formatted} {currency} in {category}. Keep tracking to unlock pattern insights."