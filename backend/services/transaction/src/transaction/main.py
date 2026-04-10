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

from transaction.config import get_settings
from transaction.database import engine
from transaction.messaging.publisher import TransactionPublisher
from transaction.routers.transaction import router as transaction_router

settings = get_settings()
logger = structlog.get_logger()


def _setup_telemetry(app: FastAPI) -> None:
    resource = Resource(attributes={"service.name": settings.otel_service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/traces")
        )
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage RabbitMQ connection lifecycle.
    One connection, one channel per service instance.
    aio_pika handles reconnection internally.
    """
    logger.info("connecting_to_rabbitmq", url=settings.rabbitmq_url)
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    app.state.publisher = TransactionPublisher(channel)
    logger.info("rabbitmq_connected")

    yield

    logger.info("closing_rabbitmq_connection")
    await connection.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Transaction Service",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _setup_telemetry(app)
    app.include_router(transaction_router)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.otel_service_name}

    return app


app = create_app()