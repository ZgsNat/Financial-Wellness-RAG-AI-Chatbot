import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from notification.database import get_db
from notification.dependencies import get_current_user_id
from notification.models.alert import AlertType
from notification.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


class AlertResponse(BaseModel):
    id: uuid.UUID
    alert_type: AlertType
    title: str
    body: str
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertListResponse(BaseModel):
    items: list[AlertResponse]
    total: int
    unread_count: int


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    unread_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
) -> AlertListResponse:
    svc = NotificationService(db)
    items, total = await svc.get_alerts_for_user(user_id, unread_only, page, page_size)
    _, unread_total = await svc.get_alerts_for_user(user_id, unread_only=True, page=1, page_size=1)
    return AlertListResponse(
        items=[AlertResponse.model_validate(a) for a in items],
        total=total,
        unread_count=unread_total,
    )


@router.patch("/{alert_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    alert_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = NotificationService(db)
    ok = await svc.mark_read(alert_id, user_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")