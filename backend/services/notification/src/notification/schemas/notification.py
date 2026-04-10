import uuid
from datetime import datetime

from pydantic import BaseModel

from notification.models.notification import NotificationType


class NotificationResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    type: NotificationType
    title: str
    body: str
    is_read: bool
    created_at: datetime
    read_at: datetime | None

    model_config = {"from_attributes": True}
