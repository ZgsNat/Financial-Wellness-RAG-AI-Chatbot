import json
import uuid
from typing import Annotated

import httpx
import structlog
from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from insight.config import get_settings
from insight.database import get_db
from insight.dependencies import get_current_user_id
from insight.rag.context_builder import build_context
from insight.rag.llm_client import GeminiQuotaExceeded, GeminiUnavailable, stream_llm
from insight.rag.preprocessor import preprocess_query
from insight.rag.retrieval import retrieve_chunks
from insight.routers.settings import REDIS_KEY_PREFIX

logger = structlog.get_logger()
settings = get_settings()

router = APIRouter(prefix="/insights", tags=["insights"])


class ChatRequest(BaseModel):
    question: str
    stream: bool = True


async def _embed_query(question: str) -> list[float]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{settings.embedding_service_url}/embed",
            json={"texts": [question], "mode": "query"},
        )
        response.raise_for_status()
        return response.json()["embeddings"][0]


@router.post("/chat")
async def chat(
    payload: Annotated[ChatRequest, Body()],
    request: Request,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    # Read user's personal API key from Redis (fallback to env key)
    redis = request.app.state.redis
    user_api_key: str | None = await redis.get(f"{REDIS_KEY_PREFIX}{user_id}")

    async def event_stream():
        try:
            # 0. Preprocess query
            question = preprocess_query(payload.question)

            # 1. Embed the user's question
            query_vector = await _embed_query(question)

            # 2. Multi-source retrieval: separate queries so transactions are
            #    never crowded out by high-similarity journal entries.
            tx_chunks = await retrieve_chunks(
                db, user_id, query_vector,
                query_text=question,
                top_k=4,
                source_types=["transaction"],
            )
            journal_chunks = await retrieve_chunks(
                db, user_id, query_vector,
                query_text=question,
                top_k=settings.rag_top_k,
                source_types=["journal_entry", "mood_entry"],
            )
            # Merge: transactions first so they're visible to context_builder
            chunks = tx_chunks + journal_chunks

            # 3. Build context string + source list
            context, sources = build_context(chunks)

            if not context:
                yield f"data: {json.dumps({'delta': 'I do not have enough context to answer that question. Please log more journal entries or transactions.'})}\n\n"
                yield f"data: {json.dumps({'done': True, 'sources': []})}\n\n"
                return

            # 4. Stream LLM response (user key takes priority over env key)
            async for delta in stream_llm(context, question, api_key=user_api_key or None):
                yield f"data: {json.dumps({'delta': delta})}\n\n"

            # 5. Send sources on completion
            yield f"data: {json.dumps({'done': True, 'sources': sources})}\n\n"

        except httpx.RequestError as exc:
            logger.error("embedding_service_unavailable", error=str(exc))
            yield f"data: {json.dumps({'error': 'Embedding service is temporarily unavailable.'})}\n\n"
        except GeminiQuotaExceeded:
            yield f"data: {json.dumps({'error': 'quota_exceeded', 'message': 'Gemini API daily quota exhausted. Please retry tomorrow after quota reset.'})}\n\n"
        except GeminiUnavailable:
            yield f"data: {json.dumps({'error': 'service_unavailable', 'message': 'Gemini đang quá tải, vui lòng thử lại sau ít phút.'})}\n\n"
        except Exception:
            logger.exception("chat_stream_error", user_id=str(user_id))
            yield f"data: {json.dumps({'error': 'An error occurred while generating the response.'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

