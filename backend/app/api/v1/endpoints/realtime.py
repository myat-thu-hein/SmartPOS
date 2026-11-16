"""Live updates (event feed and stream) and the notification center."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import (
    RESTAURANT_HEADER,
    AuthContext,
    RestaurantContext,
    client_ip,
    get_auth,
    get_restaurant_context,
    resolve_restaurant_context,
)
from app.core.config import get_settings
from app.db.session import get_db, get_session_factory
from app.schemas.common import Message
from app.schemas.realtime import EventPage, NotificationList
from app.services import realtime

router = APIRouter(tags=["realtime"])


@router.get("/events", response_model=EventPage, summary="Events after a cursor (polling transport)")
def poll_events(
    after: int | None = Query(None, ge=0, description="Cursor from the previous call; omit to start from now"),
    limit: int = Query(200, ge=1, le=500),
    ctx: RestaurantContext = Depends(get_restaurant_context),
    db: Session = Depends(get_db),
) -> EventPage:
    if after is None:
        return EventPage(events=[], cursor=realtime.latest_cursor(db, ctx.restaurant_id))
    events, cursor = realtime.events_after(db, ctx, after, limit)
    return EventPage(events=events, cursor=cursor)


def _stream_context(
    request: Request,
    restaurant_id: uuid.UUID | None = Query(None, description="EventSource cannot send headers, so pass it here"),
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> RestaurantContext:
    raw = request.headers.get(RESTAURANT_HEADER)
    chosen = restaurant_id or (uuid.UUID(raw) if raw else None)
    return resolve_restaurant_context(db, auth.user, chosen, client_ip(request))


def _poll(ctx: RestaurantContext, cursor: int) -> tuple[list, int]:
    with get_session_factory()() as db:
        return realtime.events_after(db, ctx, cursor)


def _start_cursor(ctx: RestaurantContext) -> int:
    with get_session_factory()() as db:
        return realtime.latest_cursor(db, ctx.restaurant_id)


@router.get(
    "/events/stream",
    summary="Server-Sent Events stream of live updates",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def stream_events(
    request: Request,
    after: int | None = Query(None, ge=0),
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    ctx: RestaurantContext = Depends(_stream_context),
) -> StreamingResponse:
    settings = get_settings()
    # A reconnecting EventSource sends Last-Event-ID, which is always the newest cursor.
    resume = int(last_event_id) if last_event_id and last_event_id.isdigit() else after
    cursor = resume if resume is not None else await run_in_threadpool(_start_cursor, ctx)

    async def generate():
        nonlocal cursor
        loop = asyncio.get_running_loop()
        deadline = loop.time() + settings.events_stream_seconds
        last_sent = loop.time()
        # Tell the browser how soon to reconnect, and give it the starting cursor.
        yield f"retry: 2000\nid: {cursor}\nevent: ready\ndata: {{}}\n\n"
        while loop.time() < deadline:
            if await request.is_disconnected():
                return
            events, cursor = await run_in_threadpool(_poll, ctx, cursor)
            for event in events:
                yield f"id: {event.id}\ndata: {event.model_dump_json()}\n\n"
            now = loop.time()
            if events:
                last_sent = now
            elif now - last_sent >= 15:
                # Keeps proxies from closing an idle connection and keeps Last-Event-ID current.
                yield f"id: {cursor}\nevent: ping\ndata: {{}}\n\n"
                last_sent = now
            await asyncio.sleep(settings.events_poll_interval_seconds)
        # The stream ends; the browser reconnects with Last-Event-ID and re-authenticates.

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            # no-transform stops proxies (and Next.js compression) from buffering the stream.
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/notifications", response_model=NotificationList, tags=["notifications"])
def notifications(
    limit: int = Query(30, ge=1, le=100),
    ctx: RestaurantContext = Depends(get_restaurant_context),
    db: Session = Depends(get_db),
) -> NotificationList:
    return realtime.list_notifications(db, ctx, limit)


@router.post("/notifications/read", response_model=Message, tags=["notifications"], summary="Mark all as read")
def mark_notifications_read(
    ctx: RestaurantContext = Depends(get_restaurant_context), db: Session = Depends(get_db)
) -> Message:
    realtime.mark_all_read(db, ctx)
    return Message(message="All notifications marked as read.")
