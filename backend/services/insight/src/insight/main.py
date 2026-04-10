from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import aio_pika
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from redis.asyncio import Redis

from insight.config import get_settings
from insight.database import AsyncSessionLocal, engine
from insight.messaging.consumers import setup_consumers
from insight.routers.chat import router as chat_router
from insight.routers.insight import router as insight_router
from insight.routers.settings import router as settings_router

settings = get_settings()
logger = structlog.get_logger()


def _setup_telemetry(app: FastAPI) -> None:
    resource = Resource(attributes={"service.name": settings.otel_service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/traces"))
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Redis for idempotency guards
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.redis = redis

    # RabbitMQ — one robust connection, one channel
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)  # process max 10 msgs concurrently

    # Wire up both consumers (transaction.events + journal.events)
    await setup_consumers(channel, redis, AsyncSessionLocal)
    logger.info("insight_consumers_started")

    yield

    await connection.close()
    await redis.aclose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Insight Service",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url=None,
    )
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    _setup_telemetry(app)
    app.include_router(insight_router)
    app.include_router(chat_router)
    app.include_router(settings_router)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.otel_service_name}

    return app


app = create_app()