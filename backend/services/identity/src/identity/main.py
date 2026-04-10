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

from identity.config import get_settings
from identity.database import engine
from identity.routers.auth import router as auth_router

settings = get_settings()


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


def create_app() -> FastAPI:
    app = FastAPI(
        title="Identity Service",
        version="0.1.0",
        # Don't expose docs in prod — internal service
        docs_url="/docs" if settings.debug else None,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],   # Kong handles CORS in prod; this is permissive for dev
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _setup_telemetry(app)

    app.include_router(auth_router, prefix="/auth", tags=["auth"])

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.otel_service_name}

    return app


app = create_app()