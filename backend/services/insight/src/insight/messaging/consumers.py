"""
Insight service consumes from two exchanges:
  1. transactions.events  → re-analyze spending pattern when new transaction arrives
  2. journal.events       → re-analyze mood/journal correlation when user writes

Each consumer gets its own queue bound to its respective exchange.
The queue is named explicitly and durable — survives broker restart.
If insight-service is down for an hour, messages queue up and are processed on recovery.

DLQ topology (declared here, consumed separately if needed):
  insight.transaction.created      → on nack → insight.transaction.created.dlq
  insight.journal.created          → on nack → insight.journal.created.dlq
"""

import asyncio
import uuid
from typing import Any

import aio_pika
import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from insight.messaging.base_consumer import IdempotentConsumer
from insight.rag.ingestion import ingest_document
from insight.services.insight_service import InsightService

logger = structlog.get_logger()

# Queue names — must be unique across the broker per logical consumer
TRANSACTION_QUEUE = "insight.transaction.created"
JOURNAL_QUEUE = "insight.journal.created"

TRANSACTION_EXCHANGE = "transactions.events"
JOURNAL_EXCHANGE = "journal.events"


class TransactionInsightConsumer(IdempotentConsumer):
    def __init__(self, redis: Redis, db_session_factory: Any) -> None:
        super().__init__(redis, consumer_name="insight.transaction")
        self._db_session_factory = db_session_factory

    async def process(self, body: dict[str, Any], message_id: str) -> None:
        """
        Triggered when a new transaction is created.
        Re-runs spending pattern analysis for the user.
        Phase 1: stub that logs. Phase 2: calls LLM/RAG pipeline.
        """
        user_id = body.get("user_id")
        transaction_id = body.get("transaction_id")
        event_id = body.get("event_id")

        logger.info(
            "processing_transaction_insight",
            user_id=user_id,
            transaction_id=transaction_id,
            event_id=event_id,
        )

        async with self._db_session_factory() as db:
            svc = InsightService(db)
            await svc.refresh_spending_insight(
                user_id=user_id,
                source_event_id=event_id,
                transaction_payload=body,
            )

        # Phase 2: embed + store chunk — fire and forget, does not block ACK
        if user_id and transaction_id:
            asyncio.create_task(
                ingest_document(
                    db_session_factory=self._db_session_factory,
                    source_type="transaction",
                    source_id=uuid.UUID(transaction_id),
                    user_id=uuid.UUID(user_id),
                    payload=body,
                )
            )


class JournalInsightConsumer(IdempotentConsumer):
    def __init__(self, redis: Redis, db_session_factory: Any) -> None:
        super().__init__(redis, consumer_name="insight.journal")
        self._db_session_factory = db_session_factory

    async def process(self, body: dict[str, Any], message_id: str) -> None:
        """
        Triggered when a journal entry or mood is created.
        Re-runs mood-spending correlation analysis.
        """
        user_id = body.get("user_id")
        entry_type = body.get("entry_type")  # "journal" | "mood"

        logger.info("processing_journal_insight", user_id=user_id, entry_type=entry_type)

        async with self._db_session_factory() as db:
            svc = InsightService(db)
            await svc.refresh_mood_insight(
                user_id=user_id,
                source_event_id=body.get("event_id"),
                entry_type=entry_type,
            )

        # Phase 2: embed + store chunk — fire and forget, does not block ACK
        entry_id = body.get("entry_id") or body.get("mood_id")
        source_type = "journal_entry" if entry_type == "journal" else "mood_entry"
        if user_id and entry_id:
            asyncio.create_task(
                ingest_document(
                    db_session_factory=self._db_session_factory,
                    source_type=source_type,
                    source_id=uuid.UUID(entry_id),
                    user_id=uuid.UUID(user_id),
                    payload=body,
                )
            )


async def setup_consumers(
    channel: aio_pika.abc.AbstractChannel,
    redis: Redis,
    db_session_factory: Any,
) -> None:
    """
    Declare queues, bind to exchanges, attach consumers.
    Called once during app startup.

    Dead Letter Queue setup:
      Each queue declares x-dead-letter-exchange pointing to a DLQ exchange.
      On nack(requeue=False), RabbitMQ routes the message there automatically.
      We don't consume DLQs in app code — they're inspected manually via management UI
      or a separate DLQ processor service.
    """
    # Declare DLQ exchange (fanout, routes all dead letters)
    dlq_exchange = await channel.declare_exchange("insight.dlq", aio_pika.ExchangeType.DIRECT, durable=True)

    # ── Transaction consumer ──────────────────────────────────────────────
    tx_exchange = await channel.declare_exchange(TRANSACTION_EXCHANGE, aio_pika.ExchangeType.FANOUT, durable=True)

    tx_dlq = await channel.declare_queue(f"{TRANSACTION_QUEUE}.dlq", durable=True)
    await tx_dlq.bind(dlq_exchange, routing_key=f"{TRANSACTION_QUEUE}.dlq")

    tx_queue = await channel.declare_queue(
        TRANSACTION_QUEUE,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "insight.dlq",
            "x-dead-letter-routing-key": f"{TRANSACTION_QUEUE}.dlq",
            "x-message-ttl": 86_400_000,  # 24h — stale insights not worth processing
        },
    )
    await tx_queue.bind(tx_exchange)

    tx_consumer = TransactionInsightConsumer(redis, db_session_factory)
    await tx_queue.consume(tx_consumer.handle)
    logger.info("consumer_started", queue=TRANSACTION_QUEUE)

    # ── Journal consumer ──────────────────────────────────────────────────
    journal_exchange = await channel.declare_exchange(JOURNAL_EXCHANGE, aio_pika.ExchangeType.FANOUT, durable=True)

    journal_dlq = await channel.declare_queue(f"{JOURNAL_QUEUE}.dlq", durable=True)
    await journal_dlq.bind(dlq_exchange, routing_key=f"{JOURNAL_QUEUE}.dlq")

    journal_queue = await channel.declare_queue(
        JOURNAL_QUEUE,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "insight.dlq",
            "x-dead-letter-routing-key": f"{JOURNAL_QUEUE}.dlq",
            "x-message-ttl": 86_400_000,
        },
    )
    await journal_queue.bind(journal_exchange)

    journal_consumer = JournalInsightConsumer(redis, db_session_factory)
    await journal_queue.consume(journal_consumer.handle)
    logger.info("consumer_started", queue=JOURNAL_QUEUE)