from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Body
from pydantic import BaseModel

from embedding.model import get_model

logger = structlog.get_logger()

router = APIRouter(tags=["embed"])


class EmbedRequest(BaseModel):
    texts: list[str]
    mode: Literal["query", "passage"] = "passage"


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    model: str
    dimension: int


@router.post("/embed", response_model=EmbedResponse)
async def embed(payload: Annotated[EmbedRequest, Body()]) -> EmbedResponse:
    model = get_model()

    # BGE-M3 instruction prefix — improves retrieval quality
    prefix = "query: " if payload.mode == "query" else "passage: "
    prefixed = [f"{prefix}{t}" for t in payload.texts]

    embeddings = model.encode(
        prefixed,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).tolist()

    logger.info("embedded", count=len(payload.texts), mode=payload.mode)

    return EmbedResponse(
        embeddings=embeddings,
        model=model.model_card_data.base_model or "BAAI/bge-m3",
        dimension=len(embeddings[0]) if embeddings else 1024,
    )
