"""Kitchen Display System view of orders.

Kitchen tickets are a projection of order status:
CONFIRMED -> NEW, PREPARING, READY, COMPLETED. Prices are not exposed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import RestaurantContext
from app.core.errors import ValidationFailed
from app.models import DiningTable, Order, OrderItem
from app.models.enums import OrderStatus, OrderType
from app.repositories.tenant import scoped
from app.schemas.orders import KitchenItem, KitchenTicket
from app.services.orders import change_status
from app.services.tables import display_number

KITCHEN_TO_ORDER = {
    "NEW": OrderStatus.CONFIRMED,
    "PREPARING": OrderStatus.PREPARING,
    "READY": OrderStatus.READY,
    "COMPLETED": OrderStatus.COMPLETED,
}
ORDER_TO_KITCHEN = {v: k for k, v in KITCHEN_TO_ORDER.items()}


def list_tickets(
    db: Session, ctx: RestaurantContext, statuses: list[str] | None, completed_hours: int = 12
) -> list[KitchenTicket]:
    wanted = statuses or ["NEW", "PREPARING", "READY"]
    unknown = [s for s in wanted if s not in KITCHEN_TO_ORDER]
    if unknown:
        raise ValidationFailed(f"Unknown kitchen status: {', '.join(unknown)}.")
    order_statuses = [KITCHEN_TO_ORDER[s] for s in wanted]
    stmt = (
        scoped(Order, ctx.restaurant_id)
        .where(Order.status.in_(order_statuses))
        .options(selectinload(Order.items).selectinload(OrderItem.modifiers))
    )
    if OrderStatus.COMPLETED in order_statuses:
        since = datetime.now(UTC) - timedelta(hours=completed_hours)
        stmt = stmt.where((Order.status != OrderStatus.COMPLETED) | (Order.completed_at >= since))
    orders = db.scalars(stmt.order_by(Order.confirmed_at.asc().nulls_last(), Order.created_at)).all()
    tables = (
        dict(
            db.execute(
                select(DiningTable.id, DiningTable.name).where(
                    DiningTable.id.in_({o.table_id for o in orders if o.table_id})
                )
            ).all()
        )
        if orders
        else {}
    )
    prefix = ctx.restaurant.order_number_prefix
    tickets = []
    for order in orders:
        label = f"Table {tables.get(order.table_id, '?')}" if order.order_type == OrderType.DINE_IN else "Takeaway"
        tickets.append(
            KitchenTicket(
                order_id=order.id,
                display_number=display_number(prefix, order.order_number),
                order_type=order.order_type,
                label=label,
                kitchen_status=ORDER_TO_KITCHEN[order.status],
                order_status=order.status,
                notes=order.notes,
                created_at=order.created_at,
                confirmed_at=order.confirmed_at,
                preparing_at=order.preparing_at,
                ready_at=order.ready_at,
                completed_at=order.completed_at,
                items=[
                    KitchenItem(
                        id=i.id,
                        product_name=i.product_name,
                        quantity=i.quantity,
                        modifiers=[f"{m.group_name}: {m.option_name}" for m in i.modifiers],
                        notes=i.notes,
                    )
                    for i in order.items
                ],
            )
        )
    return tickets


def update_ticket(db: Session, ctx: RestaurantContext, order_id: uuid.UUID, kitchen_status: str) -> KitchenTicket:
    change_status(db, ctx, order_id, KITCHEN_TO_ORDER[kitchen_status])
    ticket = next((t for t in list_tickets(db, ctx, list(KITCHEN_TO_ORDER)) if t.order_id == order_id), None)
    assert ticket is not None
    return ticket
