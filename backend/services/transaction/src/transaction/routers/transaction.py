import uuid
from datetime import date

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from transaction.database import get_db
from transaction.dependencies import get_current_user_id
from transaction.messaging.publisher import TransactionPublisher
from transaction.schemas.transaction import (
    TransactionCreate,
    TransactionListResponse,
    TransactionResponse,
    TransactionUpdate,
)
from transaction.services.transaction_service import TransactionService

logger = structlog.get_logger()
router = APIRouter(prefix="/transactions", tags=["transactions"])


def _get_publisher(request: Request) -> TransactionPublisher:
    """Pull the publisher from app state (set during startup)."""
    return request.app.state.publisher


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    payload: TransactionCreate,
    request: Request,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> TransactionResponse:
    svc = TransactionService(db)
    tx = await svc.create(user_id, payload)

    # Publish event AFTER commit — if publish fails, transaction is already persisted.
    # Consumers should handle eventual delivery; we log the failure and move on.
    # A more robust approach would use outbox pattern — that's a later phase.
    publisher = _get_publisher(request)
    try:
        await publisher.publish_transaction_created(tx)
    except Exception:
        logger.exception(
            "publish_failed_transaction_persisted",
            transaction_id=str(tx.id),
        )
        # Don't 500 — the transaction was saved. Insight/notification just won't fire.

    logger.info("transaction_created", transaction_id=str(tx.id), user_id=str(user_id))
    return TransactionResponse.model_validate(tx)


@router.get("", response_model=TransactionListResponse)
async def list_transactions(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
) -> TransactionListResponse:
    svc = TransactionService(db)
    items, total = await svc.list_by_user(user_id, page, page_size, date_from, date_to)
    return TransactionListResponse(
        items=[TransactionResponse.model_validate(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> TransactionResponse:
    svc = TransactionService(db)
    tx = await svc.get(transaction_id, user_id)
    if not tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return TransactionResponse.model_validate(tx)


@router.patch("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: uuid.UUID,
    payload: TransactionUpdate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> TransactionResponse:
    svc = TransactionService(db)
    tx = await svc.update(transaction_id, user_id, payload)
    if not tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return TransactionResponse.model_validate(tx)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    transaction_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = TransactionService(db)
    deleted = await svc.delete(transaction_id, user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")