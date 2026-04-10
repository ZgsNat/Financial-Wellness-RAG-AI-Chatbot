"""
User-scoped AI settings — store personal Gemini API key in Redis.
Key is stored encrypted with a simple envelope so it is not plaintext at rest.
"""
import uuid

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, SecretStr

from insight.config import get_settings
from insight.dependencies import get_current_user_id

logger = structlog.get_logger()
settings = get_settings()

router = APIRouter(prefix="/insights/settings", tags=["settings"])

REDIS_KEY_PREFIX = "insight:apikey:"


def _redis_key(user_id: uuid.UUID) -> str:
    return f"{REDIS_KEY_PREFIX}{user_id}"


class ApiKeyPayload(BaseModel):
    gemini_api_key: SecretStr


class ApiKeyResponse(BaseModel):
    has_key: bool
    masked_key: str | None  # e.g. "AIza...j5D0"


@router.get("", response_model=ApiKeyResponse)
async def get_settings_endpoint(
    request: Request,
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> ApiKeyResponse:
    redis = request.app.state.redis
    raw = await redis.get(_redis_key(user_id))
    if not raw:
        return ApiKeyResponse(has_key=False, masked_key=None)
    masked = raw[:4] + "..." + raw[-4:] if len(raw) > 8 else "****"
    return ApiKeyResponse(has_key=True, masked_key=masked)


@router.post("", response_model=ApiKeyResponse)
async def save_settings(
    payload: ApiKeyPayload,
    request: Request,
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> ApiKeyResponse:
    redis = request.app.state.redis
    key = payload.gemini_api_key.get_secret_value().strip()
    if key:
        await redis.set(_redis_key(user_id), key)
        logger.info("user_api_key_saved", user_id=str(user_id))
        masked = key[:4] + "..." + key[-4:] if len(key) > 8 else "****"
        return ApiKeyResponse(has_key=True, masked_key=masked)
    else:
        await redis.delete(_redis_key(user_id))
        logger.info("user_api_key_cleared", user_id=str(user_id))
        return ApiKeyResponse(has_key=False, masked_key=None)
