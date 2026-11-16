"""Scheduled jobs invoked by the platform (Vercel Cron), not by users."""

from __future__ import annotations

import hmac
import logging
import secrets
import time

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFound, Unauthorized
from app.db.session import get_db
from app.seed import demo as demo_seed

router = APIRouter(prefix="/internal", include_in_schema=False)
log = logging.getLogger(__name__)


def _require_cron(authorization: str | None) -> None:
    settings = get_settings()
    # Only a public demo deployment with a configured secret exposes the job at all.
    if not (settings.demo_login_enabled and settings.cron_secret):
        raise NotFound("Not found.")
    expected = f"Bearer {settings.cron_secret}"
    if not authorization or not hmac.compare_digest(authorization.encode(), expected.encode()):
        raise Unauthorized("Invalid scheduler credentials.")


@router.get("/demo/refresh")
def refresh_demo(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict[str, object]:
    """Replace the demo restaurant with fresh synthetic history ending today.

    Vercel Cron calls this with GET and ``Authorization: Bearer $CRON_SECRET``.
    Only restaurants marked ``is_demo`` are touched; demo accounts keep their passwords.
    """
    _require_cron(authorization)
    started = time.monotonic()
    # Existing demo users keep their password; a first run gets an unguessable one
    # (visitors use one-click demo sign-in, which needs no password).
    configured = get_settings().demo_password
    password = configured or secrets.token_urlsafe(24)
    result = demo_seed.refresh_demo(db, password, create_admin=False, set_password=configured is not None)
    seconds = round(time.monotonic() - started, 1)
    log.info("demo refreshed", extra={"orders": result["orders"], "seconds": seconds})
    return {"refreshed": True, "orders": result["orders"], "seconds": seconds}
