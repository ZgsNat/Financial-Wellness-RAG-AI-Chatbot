"""
Notification service consumers.

Important: notification-service has its OWN copy of IdempotentConsumer logic
(not importing from insight-service — services don't share code at runtime).
In a real project you'd extract this to an internal shared package (fw-shared).
For now, the base class is duplicated intentionally to keep services deployable independently.
"""
import json
from abc import ABC, abstractmethod
from typing import Any

import aio_pika
import structlog
from opentelemetry import trace
from opentelemetry.propagate import extract
from redis.asyncio import Redis

from notification.config import get_settings
from notification.database import AsyncSessionLocal
from notification.services.notification_service import NotificationService

logger = structlog.get_logger()
settings = get_settings()

IDEMPOTENCY_TTL = 86_400

TRANSACTION_QUEUE = "notification.transaction.created"
TRANSACTION_EXCHANGE = "transactions.events"


class IdempotentConsumer(ABC):
    def __init__(self, redis: Redis, consumer_name: str) -> None:
        self._redis = redis
        self._consumer_name = consumer_name
        self._tracer = trace.get_tracer(consumer_name)

    async def handle(self, message: aio_pika.abc.AbstractIncomingMessage) -> None:
        message_id = message.message_id or ""
        trace_ctx = extract(dict(message.headers or {}))

        with self._tracer.start_as_current_span(
            f"{self._consumer_name}.handle",
            context=trace_ctx,
            kind=trace.SpanKind.CONSUMER,
        ) as span:
            span.set_attribute("messaging.message_id", message_id)

            if message_id and await self._redis.exists(f"processed:{self._consumer_name}:{message_id}"):
                logger.info("duplicate_skipped", consumer=self._consumer_name, message_id=message_id)
                await message.ack()
                return

            try:
                body = json.loads(message.body)
                await self.process(body, message_id)
                if message_id:
                    await self._redis.setex(f"processed:{self._consumer_name}:{message_id}", IDEMPOTENCY_TTL, "1")
                await message.ack()
            except Exception as exc:
                await message.nack(requeue=False)
                span.record_exception(exc)
                logger.exception("processing_failed", consumer=self._consumer_name, error=str(exc))

    @abstractmethod
    async def process(self, body: dict[str, Any], message_id: str) -> None: ...


class TransactionNotificationConsumer(IdempotentConsumer):
    def __init__(self, redis: Redis) -> None:
        super().__init__(redis, consumer_name="notification.transaction")

    async def process(self, body: dict[str, Any], message_id: str) -> None:
        async with AsyncSessionLocal() as db:
            svc = NotificationService(db, spending_threshold=settings.spending_spike_threshold_vnd)
            alerts = await svc.evaluate_transaction(
                user_id=body.get("user_id", ""),
                payload=body,
                source_event_id=body.get("event_id"),
            )
            if alerts:
                logger.info("alerts_created", count=len(alerts), user_id=body.get("user_id"))


async def setup_consumers(channel: aio_pika.abc.AbstractChannel, redis: Redis) -> None:
    dlq_exchange = await channel.declare_exchange("notification.dlq", aio_pika.ExchangeType.DIRECT, durable=True)

    tx_exchange = await channel.declare_exchange(TRANSACTION_EXCHANGE, aio_pika.ExchangeType.FANOUT, durable=True)

    tx_dlq = await channel.declare_queue(f"{TRANSACTION_QUEUE}.dlq", durable=True)
    await tx_dlq.bind(dlq_exchange, routing_key=f"{TRANSACTION_QUEUE}.dlq")

    tx_queue = await channel.declare_queue(
        TRANSACTION_QUEUE,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "notification.dlq",
            "x-dead-letter-routing-key": f"{TRANSACTION_QUEUE}.dlq",
            "x-message-ttl": 86_400_000,
        },
    )
    await tx_queue.bind(tx_exchange)

    consumer = TransactionNotificationConsumer(redis)
    await tx_queue.consume(consumer.handle)
    logger.info("consumer_started", queue=TRANSACTION_QUEUE)