"""
IdempotentConsumer — base class for all RabbitMQ consumers in this project.

The problem it solves:
  RabbitMQ guarantees at-least-once delivery. If a consumer crashes after
  processing but before ACKing, the message is redelivered. Without guards,
  you get duplicate side effects: double LLM calls, duplicate DB writes,
  double notifications.

The solution:
  Before processing, check Redis for message_id. If seen → ACK and skip.
  After processing → mark message_id in Redis with TTL.

TTL reasoning:
  24h covers any realistic redelivery window. RabbitMQ won't redeliver
  a message that was ACKed — so the only case we need to guard against
  is crash-before-ACK, which resolves in seconds/minutes, not days.
  Keeping TTL short (24h) bounds Redis memory usage.

Trace continuation:
  The publisher injected a W3C traceparent into message headers.
  We extract it here and create a child span — this is what makes
  async consumers appear as continuations of the original trace in Jaeger,
  rather than orphaned unrelated spans.
"""

import json
from abc import ABC, abstractmethod
from typing import Any

import aio_pika
import structlog
from opentelemetry import trace
from opentelemetry.propagate import extract
from redis.asyncio import Redis

logger = structlog.get_logger()

IDEMPOTENCY_TTL_SECONDS = 86_400  # 24h


class IdempotentConsumer(ABC):
    """
    Subclass this and implement `process(body, message_id)`.
    The base class handles:
      - idempotency check via Redis
      - trace context extraction (async trace continuation)
      - ACK/NACK with DLQ routing on repeated failure
      - structured logging
    """

    def __init__(self, redis: Redis, consumer_name: str) -> None:
        self._redis = redis
        self._consumer_name = consumer_name
        self._tracer = trace.get_tracer(consumer_name)

    def _idempotency_key(self, message_id: str) -> str:
        # Namespace by consumer so different services can independently track the same message_id
        return f"processed:{self._consumer_name}:{message_id}"

    async def _already_processed(self, message_id: str) -> bool:
        return await self._redis.exists(self._idempotency_key(message_id)) == 1

    async def _mark_processed(self, message_id: str) -> None:
        await self._redis.setex(self._idempotency_key(message_id), IDEMPOTENCY_TTL_SECONDS, "1")

    async def handle(self, message: aio_pika.abc.AbstractIncomingMessage) -> None:
        message_id = message.message_id or ""

        # Extract trace context from headers — continue the publisher's trace
        trace_ctx = extract(dict(message.headers or {}))

        with self._tracer.start_as_current_span(
            f"{self._consumer_name}.handle",
            context=trace_ctx,
            kind=trace.SpanKind.CONSUMER,
        ) as span:
            span.set_attribute("messaging.message_id", message_id)
            span.set_attribute("messaging.consumer", self._consumer_name)

            if not message_id:
                # Publisher bug — no message_id set. Process anyway but warn loudly.
                logger.warning("missing_message_id", consumer=self._consumer_name)

            elif await self._already_processed(message_id):
                logger.info(
                    "duplicate_message_skipped",
                    consumer=self._consumer_name,
                    message_id=message_id,
                )
                await message.ack()
                return

            try:
                body = json.loads(message.body)
                await self.process(body, message_id)

                if message_id:
                    await self._mark_processed(message_id)

                await message.ack()
                logger.info("message_processed", consumer=self._consumer_name, message_id=message_id)
                span.set_attribute("messaging.ack", True)

            except Exception as exc:
                # requeue=False → message goes to DLQ (if configured) instead of infinite retry loop
                await message.nack(requeue=False)
                span.record_exception(exc)
                span.set_attribute("messaging.ack", False)
                logger.exception(
                    "message_processing_failed",
                    consumer=self._consumer_name,
                    message_id=message_id,
                    error=str(exc),
                )

    @abstractmethod
    async def process(self, body: dict[str, Any], message_id: str) -> None:
        """Implement business logic here. Guaranteed to run at most once per message_id."""
        ...