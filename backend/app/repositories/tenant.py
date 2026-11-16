"""Tenant-scoped data access helpers.

Every restaurant-owned query goes through these helpers (or adds an explicit
``restaurant_id`` filter) so a record from another restaurant is reported as
"not found" rather than being readable or writable.
"""

from __future__ import annotations

import uuid
from typing import Any, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound

M = TypeVar("M")


def scoped(model: type[M], restaurant_id: uuid.UUID) -> Select[tuple[M]]:
    return select(model).where(model.restaurant_id == restaurant_id)  # type: ignore[attr-defined]


def get_owned(
    db: Session,
    model: type[M],
    obj_id: uuid.UUID,
    restaurant_id: uuid.UUID,
    label: str,
    *,
    for_update: bool = False,
    options: tuple[Any, ...] = (),
) -> M:
    stmt = scoped(model, restaurant_id).where(model.id == obj_id)  # type: ignore[attr-defined]
    if options:
        stmt = stmt.options(*options)
    if for_update:
        stmt = stmt.with_for_update()
    obj = db.scalar(stmt)
    if obj is None:
        raise NotFound(f"{label} not found.")
    return obj
