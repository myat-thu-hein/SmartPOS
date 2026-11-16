"""Audit logging for sensitive operations.

Audit entries are added to the caller's database session so they are committed
atomically with the operation they describe. Never put secrets or full personal
data in `details`.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import request_id_var
from app.models import AuditLog


def record_audit(
    db: Session,
    *,
    action: str,
    actor_user_id: uuid.UUID | None,
    restaurant_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        action=action,
        actor_user_id=actor_user_id,
        restaurant_id=restaurant_id,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=_jsonable(details) if details else None,
        ip_address=ip_address,
        request_id=request_id_var.get(),
    )
    db.add(entry)
    return entry


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)
