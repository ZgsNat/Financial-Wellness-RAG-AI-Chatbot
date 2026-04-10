import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from insight.database import AsyncSessionLocal, get_db
from insight.dependencies import get_current_user_id
from insight.models.insight import InsightType
from insight.rag.ingestion import ingest_document
from insight.services.insight_service import InsightService

router = APIRouter(prefix="/insights", tags=["insights"])


class InsightResponse(BaseModel):
    id: uuid.UUID
    insight_type: InsightType
    summary: str
    detail: str | None
    updated_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[InsightResponse])
async def get_my_insights(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[InsightResponse]:
    svc = InsightService(db)
    insights = await svc.get_insights_for_user(user_id)
    return [InsightResponse.model_validate(i) for i in insights]


class ReindexRequest(BaseModel):
    source_type: str   # "transaction" | "journal_entry" | "mood_entry"
    source_id: uuid.UUID
    payload: dict[str, Any]


@router.post("/reindex", status_code=202)
async def reindex_document(
    body: ReindexRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> dict[str, str]:
    """Re-embed and upsert a single document chunk for the authenticated user.

    Useful when historical records were indexed without all fields (e.g. note
    was missing from the original event). The user_id from JWT is always used —
    the caller cannot re-index documents belonging to other users.
    """
    await ingest_document(
        db_session_factory=AsyncSessionLocal,
        source_type=body.source_type,
        source_id=body.source_id,
        user_id=user_id,
        payload=body.payload,
    )
    return {"status": "accepted"}