"""
NotificationService — evaluates rule conditions and persists alerts.

Phase 1 rules:
  Transaction event:
    - amount > threshold → SPENDING_SPIKE alert
    - category == "shopping" → CATEGORY_OVERLOAD warning (simplified; full impl needs history)

Phase 2:
  - Consume insight-service output events and generate AI-worded alerts
  - Cross-signal: check if transaction.category == shopping AND recent mood score <= 2
    (this requires querying journal-service or a read-through cache — phase 2 problem)
"""
import uuid
from decimal import Decimal, InvalidOperation

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from notification.models.alert import Alert, AlertType

logger = structlog.get_logger()


class NotificationService:
    def __init__(self, db: AsyncSession, spending_threshold: int = 500_000) -> None:
        self._db = db
        self._spending_threshold = spending_threshold

    async def evaluate_transaction(
        self,
        user_id: str,
        payload: dict,
        source_event_id: str | None,
    ) -> list[Alert]:
        """
        Evaluate a transaction event against all rules.
        Returns list of alerts created (may be empty if no rules fired).
        """
        alerts: list[Alert] = []
        uid = uuid.UUID(user_id)
        eid = uuid.UUID(source_event_id) if source_event_id else None

        # Rule 1: spending spike
        try:
            amount = Decimal(payload.get("amount", "0"))
            if payload.get("type") == "expense" and amount > self._spending_threshold:
                alert = await self._create_alert(
                    user_id=uid,
                    alert_type=AlertType.SPENDING_SPIKE,
                    title="Large expense detected",
                    body=(
                        f"You just spent {amount:,.0f} {payload.get('currency', 'VND')} "
                        f"on {payload.get('category', 'unknown')}. "
                        "Is this planned?"
                    ),
                    source_event_id=eid,
                )
                alerts.append(alert)
        except InvalidOperation:
            logger.warning("invalid_amount_in_payload", payload=payload)

        # Rule 2: shopping category — always flag for context (mild tip, not alarm)
        if payload.get("category") == "shopping" and payload.get("type") == "expense":
            alert = await self._create_alert(
                user_id=uid,
                alert_type=AlertType.CATEGORY_OVERLOAD,
                title="Shopping logged",
                body=(
                    "Shopping expense recorded. "
                    "Keep an eye on your shopping pattern — logging your mood today can help spot trends."
                ),
                source_event_id=eid,
            )
            alerts.append(alert)

        return alerts

    async def get_alerts_for_user(
        self,
        user_id: uuid.UUID,
        unread_only: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Alert], int]:
        from sqlalchemy import func

        q = select(Alert).where(Alert.user_id == user_id)
        if unread_only:
            q = q.where(Alert.is_read == False)  # noqa: E712

        total = (await self._db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
        items = (
            await self._db.execute(
                q.order_by(Alert.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        return list(items), total

    async def mark_read(self, alert_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        result = await self._db.execute(
            select(Alert).where(Alert.id == alert_id, Alert.user_id == user_id)
        )
        alert = result.scalar_one_or_none()
        if not alert:
            return False
        alert.is_read = True
        await self._db.commit()
        return True

    async def _create_alert(
        self,
        user_id: uuid.UUID,
        alert_type: AlertType,
        title: str,
        body: str,
        source_event_id: uuid.UUID | None,
    ) -> Alert:
        alert = Alert(
            user_id=user_id,
            alert_type=alert_type,
            title=title,
            body=body,
            source_event_id=source_event_id,
        )
        self._db.add(alert)
        await self._db.commit()
        await self._db.refresh(alert)
        logger.info("alert_created", alert_id=str(alert.id), alert_type=alert_type, user_id=str(user_id))
        return alert