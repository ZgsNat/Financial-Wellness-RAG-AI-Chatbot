import uuid
from datetime import datetime, timezone

import aio_pika
import structlog
from opentelemetry import trace
from opentelemetry.propagate import inject

from journal.models.journal import JournalEntry, MoodEntry
from journal.schemas.journal import JournalEntryCreatedEvent

logger = structlog.get_logger()

EXCHANGE_NAME = "journal.events"


class JournalPublisher:
    def __init__(self, channel: aio_pika.abc.AbstractChannel) -> None:
        self._channel = channel
        self._exchange: aio_pika.abc.AbstractExchange | None = None

    async def _get_exchange(self) -> aio_pika.abc.AbstractExchange:
        if self._exchange is None:
            self._exchange = await self._channel.declare_exchange(
                EXCHANGE_NAME,
                aio_pika.ExchangeType.FANOUT,
                durable=True,
            )
        return self._exchange

    async def _publish(self, event: JournalEntryCreatedEvent) -> None:
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("publish_journal_event") as span:
            span.set_attribute("journal.entry_type", event.entry_type)
            span.set_attribute("messaging.destination", EXCHANGE_NAME)

            headers: dict[str, str] = {}
            inject(headers)

            exchange = await self._get_exchange()
            await exchange.publish(
                aio_pika.Message(
                    body=event.model_dump_json().encode(),
                    content_type="application/json",
                    message_id=str(event.event_id),
                    headers=headers, #type: ignore
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key="",
            )
            logger.info("journal_event_published", event_id=str(event.event_id), entry_type=event.entry_type)

    async def publish_journal_created(self, entry: JournalEntry) -> None:
        await self._publish(
            JournalEntryCreatedEvent(
                event_id=uuid.uuid4(),
                entry_type="journal",
                entry_id=entry.id,
                user_id=entry.user_id,
                occurred_at=datetime.now(timezone.utc).isoformat(),
                content=entry.content,
                created_at=entry.created_at.isoformat(),
            )
        )

    async def publish_mood_created(self, entry: MoodEntry) -> None:
        await self._publish(
            JournalEntryCreatedEvent(
                event_id=uuid.uuid4(),
                entry_type="mood",
                entry_id=entry.id,
                user_id=entry.user_id,
                occurred_at=datetime.now(timezone.utc).isoformat(),
                score=entry.score,
                note=entry.note,
                created_at=entry.created_at.isoformat(),
            )
        )