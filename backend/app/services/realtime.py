"""Live updates: the event feed and the notification center.

``emit`` adds an event to the caller's transaction, so a change and its event
commit or roll back together (transactional outbox). Clients read the feed
after a cursor, either by polling ``GET /events`` or through the
``/events/stream`` Server-Sent Events endpoint, and re-fetch whatever they
display. Event payloads hold identifiers and statuses only, never money
amounts or personal data.
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, true
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.api.deps import RestaurantContext
from app.core.permissions import Permission
from app.models import Notification, NotificationCursor, RealtimeEvent
from app.schemas.realtime import EventOut, NotificationList, NotificationOut

EVENT_RETENTION = timedelta(days=2)
NOTIFICATION_WINDOW = timedelta(days=30)

# Who may see events of each topic (any one of the permissions is enough).
TOPIC_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "order": frozenset({Permission.ORDERS_READ, Permission.KITCHEN_READ}),
    "table": frozenset({Permission.TABLES_READ}),
    "stock": frozenset({Permission.INVENTORY_READ}),
    "po": frozenset({Permission.PURCHASING_READ}),
    "supplier": frozenset({Permission.SUPPLIERS_READ}),
    "recommendations": frozenset({Permission.RECOMMENDATIONS_READ}),
    "forecast": frozenset({Permission.FORECAST_READ}),
    "menu": frozenset({Permission.MENU_READ}),
    "settings": frozenset({Permission.MENU_READ}),
    "customer": frozenset({Permission.CUSTOMERS_READ}),
}


def emit(
    db: Session,
    restaurant_id: uuid.UUID,
    event_type: str,
    *,
    entity_id: uuid.UUID | str | None = None,
    data: dict[str, Any] | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> None:
    """Record an event in the current transaction. ``event_type`` is ``topic.action``."""
    topic = event_type.split(".", 1)[0]
    db.add(
        RealtimeEvent(
            restaurant_id=restaurant_id,
            topic=topic,
            type=event_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            data=data or {},
            actor_user_id=actor_user_id,
        )
    )
    if random.random() < 0.01:  # noqa: S311 - housekeeping, not security
        db.execute(delete(RealtimeEvent).where(RealtimeEvent.created_at < datetime.now(UTC) - EVENT_RETENTION))


def notify(
    db: Session,
    restaurant_id: uuid.UUID,
    *,
    kind: str,
    title: str,
    permission: Permission,
    severity: str = "info",
    body: str | None = None,
    link: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> None:
    """Create a persisted notification and announce it on the event feed."""
    notification = Notification(
        restaurant_id=restaurant_id,
        kind=kind,
        severity=severity,
        title=title[:200],
        body=body[:500] if body else None,
        link=link,
        permission=permission.value,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
    )
    db.add(notification)
    db.flush()
    emit(
        db,
        restaurant_id,
        "notification.created",
        entity_id=notification.id,
        data={
            "kind": kind,
            "severity": severity,
            "title": notification.title,
            "body": notification.body,
            "link": link,
            "permission": permission.value,
        },
        actor_user_id=actor_user_id,
    )


def _visible(ctx: RestaurantContext, event: RealtimeEvent) -> bool:
    if event.topic == "notification":
        return Permission(event.data.get("permission", Permission.PLATFORM_ADMIN.value)) in ctx.permissions
    allowed = TOPIC_PERMISSIONS.get(event.topic)
    return allowed is None or bool(allowed & ctx.permissions)


def latest_cursor(db: Session, restaurant_id: uuid.UUID) -> int:
    return int(db.scalar(select(func.max(RealtimeEvent.id)).where(RealtimeEvent.restaurant_id == restaurant_id)) or 0)


def events_after(db: Session, ctx: RestaurantContext, after: int, limit: int = 200) -> tuple[list[EventOut], int]:
    """Events newer than ``after`` that this user may see, and the new cursor."""
    rows = db.scalars(
        select(RealtimeEvent)
        .where(RealtimeEvent.restaurant_id == ctx.restaurant_id, RealtimeEvent.id > after)
        .order_by(RealtimeEvent.id)
        .limit(limit)
    ).all()
    cursor = rows[-1].id if rows else after
    return [EventOut.model_validate(r) for r in rows if _visible(ctx, r)], cursor


# --------------------------------------------------------------------------- notifications


def _read_up_to(db: Session, ctx: RestaurantContext) -> datetime | None:
    return db.scalar(
        select(NotificationCursor.read_up_to).where(
            NotificationCursor.user_id == ctx.user_id, NotificationCursor.restaurant_id == ctx.restaurant_id
        )
    )


def list_notifications(db: Session, ctx: RestaurantContext, limit: int = 30) -> NotificationList:
    since = datetime.now(UTC) - NOTIFICATION_WINDOW
    visible = [p.value for p in ctx.permissions]
    base = select(Notification).where(
        Notification.restaurant_id == ctx.restaurant_id,
        Notification.created_at >= since,
        Notification.permission.in_(visible),
    )
    rows = db.scalars(base.order_by(Notification.created_at.desc()).limit(limit)).all()
    read_up_to = _read_up_to(db, ctx)
    unread_filter = Notification.created_at > read_up_to if read_up_to else true()
    unread = int(db.scalar(select(func.count()).select_from(base.where(unread_filter).subquery())) or 0)
    return NotificationList(
        items=[
            NotificationOut.model_validate(n).model_copy(
                update={"unread": read_up_to is None or n.created_at > read_up_to}
            )
            for n in rows
        ],
        unread_count=unread,
    )


def mark_all_read(db: Session, ctx: RestaurantContext) -> None:
    now = datetime.now(UTC)
    db.execute(
        insert(NotificationCursor)
        .values(user_id=ctx.user_id, restaurant_id=ctx.restaurant_id, read_up_to=now)
        .on_conflict_do_update(
            index_elements=[NotificationCursor.user_id, NotificationCursor.restaurant_id], set_={"read_up_to": now}
        )
    )
    db.commit()
