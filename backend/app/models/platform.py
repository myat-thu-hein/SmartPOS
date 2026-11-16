"""Platform infrastructure tables that are not business records."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, uuid_pk


class RateLimitBucket(Base):
    """Attempt counter for one key in one fixed time window.

    Kept in the database so limits hold across processes and serverless
    instances, where in-memory counters would each allow the full quota.
    """

    __tablename__ = "rate_limit_buckets"
    __table_args__ = (Index("ix_rate_limit_buckets_window_start", "window_start"),)

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class RealtimeEvent(Base):
    """Append-only feed of business changes for live updates (a transactional outbox).

    Rows are written in the same transaction as the change they describe, so a
    rolled-back change never produces an event. The bigint id is the cursor that
    clients resume from. Payloads stay small and carry no money amounts or
    personal data: clients re-fetch what they display.
    """

    __tablename__ = "realtime_events"
    __table_args__ = (Index("ix_realtime_events_restaurant_cursor", "restaurant_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False)
    topic: Mapped[str] = mapped_column(String(40), nullable=False)
    type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at_col()


class Notification(Base):
    """A persisted alert shown in the notification center (low stock, deliveries...)."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_restaurant_created", "restaurant_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(String(500))
    link: Mapped[str | None] = mapped_column(String(200))
    # Only members whose role has this permission see the notification.
    permission: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_at_col()


class NotificationCursor(Base):
    """How far each user has read a restaurant's notifications."""

    __tablename__ = "notification_cursors"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), primary_key=True)
    read_up_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
