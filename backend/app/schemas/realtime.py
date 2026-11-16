"""Live-update events and notifications."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.common import ORMModel


class EventOut(ORMModel):
    id: int
    type: str
    topic: str
    entity_id: str | None
    data: dict[str, Any]
    actor_user_id: uuid.UUID | None
    created_at: datetime


class EventPage(BaseModel):
    events: list[EventOut]
    cursor: int


class NotificationOut(ORMModel):
    id: uuid.UUID
    kind: str
    severity: str
    title: str
    body: str | None
    link: str | None
    entity_type: str | None
    entity_id: str | None
    created_at: datetime
    unread: bool = False


class NotificationList(BaseModel):
    items: list[NotificationOut]
    unread_count: int
