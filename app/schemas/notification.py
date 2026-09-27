from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    message: str
    category: str
    data: dict[str, Any] = Field(default_factory=dict)
    is_read: bool = False
    push_sent: bool = False
    created_at: datetime
    read_at: Optional[datetime] = None


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse] = Field(default_factory=list)
    unread_count: int = 0


class PushSubscriptionRequest(BaseModel):
    endpoint: str = Field(..., min_length=1, max_length=500)
    p256dh: str = Field(..., min_length=1, max_length=200)
    auth: str = Field(..., min_length=1, max_length=200)


class PushSubscriptionResponse(BaseModel):
    endpoint: str
    vapid_public_key: str = ""


class UnsubscribeRequest(BaseModel):
    endpoint: str = Field(..., min_length=1, max_length=500)


class UnreadCountResponse(BaseModel):
    count: int = 0
