from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import structlog
from fastapi import FastAPI

from embedding.config import get_settings
from embedding.model import get_model, load_model
from embedding.routers.embed import router as embed_router

settings = get_settings()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("loading_embedding_model", model=settings.model_name)
    model = load_model(settings.model_name)
    logger.info("embedding_model_ready", model=settings.model_name)
    app.state.model = model
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Embedding Service", version="0.1.0", lifespan=lifespan)
    app.include_router(embed_router)

    @app.get("/health")
    async def health() -> dict:
        try:
            get_model()
            model_loaded = True
        except RuntimeError:
            model_loaded = False
        return {"status": "ok", "model_loaded": model_loaded}

    return app


app = create_app()
