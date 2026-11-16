"""Dining tables and their status lifecycle.

Status rules:
* OCCUPIED is set only by starting a dine-in order on the table.
* A table with an active order cannot be manually freed; it must be closed,
  which requires every order on it to be completed and paid, or cancelled.
* Closing moves the table to CLEANING; staff then mark it AVAILABLE.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import RestaurantContext
from app.core.errors import Conflict, ValidationFailed
from app.models import DiningTable, Order, OrderItem
from app.models.enums import OrderStatus, PaymentStatus, TableStatus
from app.repositories.tenant import get_owned, scoped
from app.schemas.catalog import TableCreate, TableOrderSummary, TableOut, TableUpdate
from app.services import realtime
from app.services.audit import record_audit

ACTIVE_ORDER_STATUSES = (OrderStatus.DRAFT, OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.READY)
SETTLED_PAYMENT = (PaymentStatus.PAID, PaymentStatus.PARTIALLY_REFUNDED, PaymentStatus.REFUNDED)

MANUAL_TRANSITIONS: dict[TableStatus, set[TableStatus]] = {
    TableStatus.AVAILABLE: {TableStatus.RESERVED, TableStatus.CLEANING},
    TableStatus.RESERVED: {TableStatus.AVAILABLE, TableStatus.CLEANING},
    TableStatus.CLEANING: {TableStatus.AVAILABLE, TableStatus.RESERVED},
    TableStatus.OCCUPIED: set(),
}


def display_number(prefix: str, number: int) -> str:
    return f"{prefix}{number:04d}"


def _summaries(db: Session, ctx: RestaurantContext, order_ids: set[uuid.UUID]) -> dict[uuid.UUID, TableOrderSummary]:
    if not order_ids:
        return {}
    counts = dict(
        db.execute(
            select(OrderItem.order_id, func.coalesce(func.sum(OrderItem.quantity), 0))
            .where(OrderItem.order_id.in_(order_ids))
            .group_by(OrderItem.order_id)
        ).all()
    )
    orders = db.scalars(scoped(Order, ctx.restaurant_id).where(Order.id.in_(order_ids))).all()
    prefix = ctx.restaurant.order_number_prefix
    return {
        o.id: TableOrderSummary(
            id=o.id,
            order_number=o.order_number,
            display_number=display_number(prefix, o.order_number),
            status=o.status.value,
            payment_status=o.payment_status.value,
            total_minor=o.total_minor,
            item_count=int(counts.get(o.id, 0)),
            created_at=o.created_at,
        )
        for o in orders
    }


def _out(table: DiningTable, summaries: dict[uuid.UUID, TableOrderSummary]) -> TableOut:
    out = TableOut.model_validate(table)
    if table.current_order_id:
        out.current_order = summaries.get(table.current_order_id)
    return out


def list_tables(db: Session, ctx: RestaurantContext, include_inactive: bool) -> list[TableOut]:
    stmt = scoped(DiningTable, ctx.restaurant_id)
    if not include_inactive:
        stmt = stmt.where(DiningTable.is_active.is_(True))
    tables = db.scalars(stmt.order_by(DiningTable.zone.nulls_last(), DiningTable.name)).all()
    summaries = _summaries(db, ctx, {t.current_order_id for t in tables if t.current_order_id})
    return [_out(t, summaries) for t in tables]


def get_table_out(db: Session, ctx: RestaurantContext, table_id: uuid.UUID) -> TableOut:
    table = get_owned(db, DiningTable, table_id, ctx.restaurant_id, "Table")
    return _out(table, _summaries(db, ctx, {table.current_order_id} if table.current_order_id else set()))


def _unique_name(db: Session, ctx: RestaurantContext, name: str, exclude: uuid.UUID | None = None) -> None:
    stmt = scoped(DiningTable, ctx.restaurant_id).where(func.lower(DiningTable.name) == name.lower())
    if exclude:
        stmt = stmt.where(DiningTable.id != exclude)
    if db.scalar(stmt):
        raise Conflict("A table with this name already exists.")


def create_table(db: Session, ctx: RestaurantContext, data: TableCreate) -> TableOut:
    _unique_name(db, ctx, data.name.strip())
    table = DiningTable(restaurant_id=ctx.restaurant_id, **{**data.model_dump(), "name": data.name.strip()})
    db.add(table)
    realtime.emit(db, ctx.restaurant_id, "table.changed", actor_user_id=ctx.user_id)
    db.commit()
    return _out(table, {})


def update_table(db: Session, ctx: RestaurantContext, table_id: uuid.UUID, data: TableUpdate) -> TableOut:
    table = get_owned(db, DiningTable, table_id, ctx.restaurant_id, "Table", for_update=True)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("name"):
        changes["name"] = changes["name"].strip()
        _unique_name(db, ctx, changes["name"], exclude=table.id)
    if changes.get("is_active") is False and active_orders_on_table(db, table.id):
        raise Conflict("This table has active orders and cannot be deactivated.")
    for field, value in changes.items():
        if value is not None or field in {"zone", "layout_x", "layout_y"}:
            setattr(table, field, value)
    realtime.emit(db, ctx.restaurant_id, "table.changed", actor_user_id=ctx.user_id)
    db.commit()
    return get_table_out(db, ctx, table.id)


def active_orders_on_table(db: Session, table_id: uuid.UUID) -> list[Order]:
    return list(
        db.scalars(select(Order).where(Order.table_id == table_id, Order.status.in_(ACTIVE_ORDER_STATUSES))).all()
    )


def set_status(db: Session, ctx: RestaurantContext, table_id: uuid.UUID, status: TableStatus) -> TableOut:
    table = get_owned(db, DiningTable, table_id, ctx.restaurant_id, "Table", for_update=True)
    if status == table.status:
        return get_table_out(db, ctx, table.id)
    if status == TableStatus.OCCUPIED:
        raise ValidationFailed("Tables become occupied automatically when a dine-in order is started.")
    if status not in MANUAL_TRANSITIONS[table.status]:
        message = (
            "Close the table's order first."
            if table.status == TableStatus.OCCUPIED
            else f"A table cannot change from {table.status.value} to {status.value}."
        )
        raise Conflict(message, code="invalid_table_transition")
    table.status = status
    realtime.emit(db, ctx.restaurant_id, "table.changed", actor_user_id=ctx.user_id)
    db.commit()
    return get_table_out(db, ctx, table.id)


def close_table(db: Session, ctx: RestaurantContext, table_id: uuid.UUID) -> TableOut:
    table = get_owned(db, DiningTable, table_id, ctx.restaurant_id, "Table", for_update=True)
    if table.status != TableStatus.OCCUPIED:
        raise Conflict("Only occupied tables can be closed.", code="table_not_occupied")
    open_orders = db.scalars(
        select(Order).where(
            Order.table_id == table.id,
            Order.status != OrderStatus.CANCELLED,
            Order.payment_status.not_in(SETTLED_PAYMENT),
        )
    ).all()
    unfinished = db.scalars(
        select(Order).where(Order.table_id == table.id, Order.status.in_(ACTIVE_ORDER_STATUSES))
    ).all()
    if open_orders or unfinished:
        prefix = ctx.restaurant.order_number_prefix
        numbers = sorted({display_number(prefix, o.order_number) for o in [*open_orders, *unfinished]})
        raise Conflict(
            "All orders on this table must be completed and paid (or cancelled) before closing it.",
            code="table_has_open_orders",
            details={"orders": numbers},
        )
    table.status = TableStatus.CLEANING
    table.current_order_id = None
    record_audit(
        db,
        action="table.closed",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="table",
        entity_id=table.id,
        ip_address=ctx.ip,
    )
    realtime.emit(db, ctx.restaurant_id, "table.changed", actor_user_id=ctx.user_id)
    db.commit()
    return get_table_out(db, ctx, table.id)


def delete_table(db: Session, ctx: RestaurantContext, table_id: uuid.UUID) -> str:
    table = get_owned(db, DiningTable, table_id, ctx.restaurant_id, "Table", for_update=True)
    if active_orders_on_table(db, table.id):
        raise Conflict("This table has active orders.")
    has_history = db.scalar(select(func.count()).select_from(Order).where(Order.table_id == table.id))
    if has_history:
        table.is_active = False
        outcome = "deactivated"
    else:
        db.delete(table)
        outcome = "deleted"
    realtime.emit(db, ctx.restaurant_id, "table.changed", actor_user_id=ctx.user_id)
    db.commit()
    return outcome
