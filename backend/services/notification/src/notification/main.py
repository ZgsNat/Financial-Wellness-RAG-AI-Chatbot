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

from notification.config import get_settings
from notification.database import engine
from notification.messaging.consumers import setup_consumers
from notification.routers.alert import router as alert_router

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
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)
    await setup_consumers(channel, redis)
    logger.info("notification_consumers_started")
    yield
    await connection.close()
    await redis.aclose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Notification Service",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url=None,
    )
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    _setup_telemetry(app)
    app.include_router(alert_router)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.otel_service_name}

    return app


app = create_app()