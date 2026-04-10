"""
RabbitMQ publisher for transaction events.

Exchange topology:
  - transactions.events   → fanout → all bound queues
      insight.transaction.created      → insight-service
      notification.transaction.created → notification-service

Each consumer creates its own queue and binds to the exchange.
transaction-service only knows the exchange name, not who's listening.
This is the loose coupling fanout gives us.
"""

import json
import uuid
from datetime import datetime, timezone

import aio_pika
import structlog
from opentelemetry import trace
from opentelemetry.propagate import inject

from transaction.config import get_settings
from transaction.models.transaction import Transaction
from transaction.schemas.transaction import TransactionCreatedEvent

logger = structlog.get_logger()
settings = get_settings()

EXCHANGE_NAME = "transactions.events"


class TransactionPublisher:
    def __init__(self, channel: aio_pika.abc.AbstractChannel) -> None:
        self._channel = channel
        self._exchange: aio_pika.abc.AbstractExchange | None = None

    async def _get_exchange(self) -> aio_pika.abc.AbstractExchange:
        if self._exchange is None:
            # declare_exchange is idempotent — safe to call on every publish
            self._exchange = await self._channel.declare_exchange(
                EXCHANGE_NAME,
                aio_pika.ExchangeType.FANOUT,
                durable=True,   # survives RabbitMQ restart
            )
        return self._exchange

    async def publish_transaction_created(self, transaction: Transaction) -> None:
        """
        Publish TransactionCreatedEvent to fanout exchange.
        Injects W3C traceparent into message headers so consumers
        can continue the trace as an async continuation.
        """
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("publish_transaction_created") as span:
            span.set_attribute("transaction.id", str(transaction.id))
            span.set_attribute("messaging.system", "rabbitmq")
            span.set_attribute("messaging.destination", EXCHANGE_NAME)

            # Build event
            event = TransactionCreatedEvent(
                event_id=uuid.uuid4(),      # unique per publish, not per transaction
                transaction_id=transaction.id,
                user_id=transaction.user_id,
                amount=str(transaction.amount),
                currency=transaction.currency,
                # SQLAlchemy may return enum as str or enum instance depending on load state
                type=getattr(transaction.type, "value", str(transaction.type)),
                category=getattr(transaction.category, "value", str(transaction.category)),
                note=transaction.note,
                transaction_date=transaction.transaction_date.isoformat(),
                occurred_at=datetime.now(timezone.utc).isoformat(),
            )

            # Propagate trace context into headers
            headers: dict[str, str] = {}
            inject(headers)   # adds traceparent (and tracestate if present)

            exchange = await self._get_exchange()
            await exchange.publish(
                aio_pika.Message(
                    body=event.model_dump_json().encode(),
                    content_type="application/json",
                    message_id=str(event.event_id),   # RabbitMQ-level dedup key
                    headers=headers, # type: ignore
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,  # survive broker restart
                ),
                routing_key="",   # fanout ignores routing key
            )

            logger.info(
                "transaction_event_published",
                event_id=str(event.event_id),
                transaction_id=str(transaction.id),
                exchange=EXCHANGE_NAME,
            )