"""
Gemini streaming LLM client.

Uses google-genai SDK (gemini-2.0-flash).
Configured once per call — stateless, safe for async contexts.
"""
from collections.abc import AsyncGenerator

from google import genai
from google.genai import types

import structlog

from insight.config import get_settings
from insight.rag.prompt import build_prompt

logger = structlog.get_logger()
settings = get_settings()


class GeminiQuotaExceeded(Exception):
    """Raised when Gemini API daily quota is exhausted (HTTP 429)."""


class GeminiUnavailable(Exception):
    """Raised when Gemini API is temporarily unavailable (HTTP 503)."""


async def stream_llm(context: str, question: str, api_key: str | None = None) -> AsyncGenerator[str, None]:
    """
    Yield text deltas from Gemini in response to *question* grounded in *context*.
    Uses *api_key* if provided, otherwise falls back to settings.gemini_api_key.
    Raises GeminiQuotaExceeded if the API daily quota is exhausted.
    """
    effective_key = api_key or settings.gemini_api_key
    client = genai.Client(api_key=effective_key)
    full_prompt = build_prompt(context, question)

    try:
        async for chunk in await client.aio.models.generate_content_stream(
            model=settings.gemini_model,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=2048,
                temperature=0.7,
            ),
        ):
            if chunk.text:
                yield chunk.text

    except Exception as exc:
        exc_str = str(exc)
        if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str or "quota" in exc_str.lower():
            logger.warning("gemini_quota_exceeded", model=settings.gemini_model, error=exc_str[:200])
            raise GeminiQuotaExceeded("Gemini API daily quota exceeded") from exc
        if "503" in exc_str or "UNAVAILABLE" in exc_str:
            logger.warning("gemini_unavailable", model=settings.gemini_model, error=exc_str[:200])
            raise GeminiUnavailable("Gemini API temporarily unavailable") from exc
        raise
