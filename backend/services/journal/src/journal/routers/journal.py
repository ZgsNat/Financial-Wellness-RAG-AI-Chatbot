import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from journal.database import get_db
from journal.dependencies import get_current_user_id
from journal.messaging.publisher import JournalPublisher
from journal.schemas.journal import (
    JournalEntryCreate,
    JournalEntryListResponse,
    JournalEntryResponse,
    JournalEntryUpdate,
    MoodEntryCreate,
    MoodEntryResponse,
)
from journal.services.journal_service import JournalService

logger = structlog.get_logger()
router = APIRouter(tags=["journal"])


def _get_publisher(request: Request) -> JournalPublisher:
    return request.app.state.publisher


# ── Mood endpoints ────────────────────────────────────────────────────────

@router.post("/moods", response_model=MoodEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_mood(
    payload: MoodEntryCreate,
    request: Request,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> MoodEntryResponse:
    svc = JournalService(db)
    entry = await svc.create_mood(user_id, payload)
    try:
        await _get_publisher(request).publish_mood_created(entry)
    except Exception:
        logger.exception("publish_failed", entry_id=str(entry.id))
    return MoodEntryResponse.model_validate(entry)


@router.get("/moods", response_model=list[MoodEntryResponse])
async def list_moods(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=90),
) -> list[MoodEntryResponse]:
    svc = JournalService(db)
    items, _ = await svc.list_moods(user_id, page, page_size)
    return [MoodEntryResponse.model_validate(e) for e in items]


# ── Journal entry endpoints ───────────────────────────────────────────────

@router.post("/entries", response_model=JournalEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_entry(
    payload: JournalEntryCreate,
    request: Request,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> JournalEntryResponse:
    svc = JournalService(db)
    entry = await svc.create_entry(user_id, payload)
    try:
        await _get_publisher(request).publish_journal_created(entry)
    except Exception:
        logger.exception("publish_failed", entry_id=str(entry.id))
    return JournalEntryResponse.model_validate(entry)


@router.get("/entries", response_model=JournalEntryListResponse)
async def list_entries(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
) -> JournalEntryListResponse:
    svc = JournalService(db)
    items, total = await svc.list_entries(user_id, page, page_size)
    return JournalEntryListResponse(
        items=[JournalEntryResponse.model_validate(e) for e in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/entries/{entry_id}", response_model=JournalEntryResponse)
async def get_entry(
    entry_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> JournalEntryResponse:
    svc = JournalService(db)
    entry = await svc.get_entry(entry_id, user_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    return JournalEntryResponse.model_validate(entry)


@router.patch("/entries/{entry_id}", response_model=JournalEntryResponse)
async def update_entry(
    entry_id: uuid.UUID,
    payload: JournalEntryUpdate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> JournalEntryResponse:
    svc = JournalService(db)
    entry = await svc.update_entry(entry_id, user_id, payload)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    return JournalEntryResponse.model_validate(entry)


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(
    entry_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = JournalService(db)
    deleted = await svc.delete_entry(entry_id, user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")