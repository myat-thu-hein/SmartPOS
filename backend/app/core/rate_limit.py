"""Sliding-window rate limiting backed by PostgreSQL.

Counters live in the database (``rate_limit_buckets``), so a limit holds across
backend processes and serverless instances. Each key keeps one row per fixed
window, and the current rate is estimated with the sliding-window-counter
method: ``current + previous * (share of the previous window still inside the
sliding window)``. Increments run in their own short transaction, so a failed
sign-in still counts even when the request that triggered it is rolled back.
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.db.session import get_session_factory
from app.models.platform import RateLimitBucket

# Rows older than this are deleted opportunistically (about 1 in 100 hits).
_RETENTION = timedelta(days=1)


def _window_start(now: datetime, window_seconds: int) -> datetime:
    epoch = now.timestamp()
    return datetime.fromtimestamp(epoch - epoch % window_seconds, tz=UTC)


class DatabaseRateLimiter:
    def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        """Register an attempt. Returns (allowed, retry_after_seconds)."""
        now = datetime.now(UTC)
        current = _window_start(now, window_seconds)
        previous = current - timedelta(seconds=window_seconds)
        with get_session_factory()() as db:
            count = db.scalar(
                insert(RateLimitBucket)
                .values(key=key, window_start=current, count=1)
                .on_conflict_do_update(
                    index_elements=[RateLimitBucket.key, RateLimitBucket.window_start],
                    set_={"count": RateLimitBucket.count + 1},
                )
                .returning(RateLimitBucket.count)
            )
            previous_count = (
                db.scalar(
                    select(RateLimitBucket.count).where(
                        RateLimitBucket.key == key, RateLimitBucket.window_start == previous
                    )
                )
                or 0
            )
            if random.random() < 0.01:  # noqa: S311 - housekeeping, not security
                db.execute(delete(RateLimitBucket).where(RateLimitBucket.window_start < now - _RETENTION))
            db.commit()
        elapsed = (now - current).total_seconds()
        weight = 1 - elapsed / window_seconds
        estimated = (count or 0) + previous_count * weight
        if estimated <= limit:
            return True, 0
        # The previous window's weight falls linearly; wait until the estimate fits again,
        # or at most until the current window ends.
        if previous_count:
            needed = (estimated - limit) / previous_count * window_seconds
            retry_after = min(needed, window_seconds - elapsed)
        else:
            retry_after = window_seconds - elapsed
        return False, max(1, math.ceil(retry_after))

    def reset(self, key: str | None = None) -> None:
        with get_session_factory()() as db:
            stmt = delete(RateLimitBucket)
            if key is not None:
                stmt = stmt.where(RateLimitBucket.key == key)
            db.execute(stmt)
            db.commit()


login_limiter = DatabaseRateLimiter()
ai_limiter = DatabaseRateLimiter()
