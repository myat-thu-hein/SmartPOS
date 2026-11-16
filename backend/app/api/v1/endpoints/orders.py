"""Orders, payments, refunds, receipts and the kitchen display."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import RestaurantContext, require
from app.core.errors import Forbidden
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import Payment
from app.models.enums import OrderStatus, OrderType, PaymentStatus
from app.repositories.tenant import scoped
from app.schemas.common import Page, PageParams, paginate
from app.schemas.orders import (
    CancelRequest,
    CancelResult,
    KitchenStatusChange,
    KitchenTicket,
    OrderCreate,
    OrderDraftIn,
    OrderListItem,
    OrderOut,
    OrderQuote,
    OrderUpdate,
    PaymentCreate,
    PaymentOut,
    Receipt,
    RefundCreate,
    StatusChange,
)
from app.services import kitchen as kitchen_service
from app.services import orders as order_service
from app.services.receipts import build_receipt
from app.utils.types import IdempotencyKey

router = APIRouter()
REPLAY_HEADER = "Idempotent-Replayed"


def _idempotency_key(key: IdempotencyKey | None = Header(None, alias="Idempotency-Key")) -> str | None:
    return key


@router.post(
    "/orders/quote",
    response_model=OrderQuote,
    tags=["orders"],
    summary="Price a cart without saving it (authoritative totals)",
)
def quote(
    data: OrderDraftIn,
    ctx: RestaurantContext = Depends(require(Permission.ORDERS_CREATE)),
    db: Session = Depends(get_db),
) -> OrderQuote:
    return order_service.quote(db, ctx, data)


@router.post("/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED, tags=["orders"])
def create_order(
    data: OrderCreate,
    response: Response,
    key: str | None = Depends(_idempotency_key),
    ctx: RestaurantContext = Depends(require(Permission.ORDERS_CREATE)),
    db: Session = Depends(get_db),
) -> OrderOut:
    order, replayed = order_service.create_order(db, ctx, data, key)
    if replayed:
        response.status_code = status.HTTP_200_OK
        response.headers[REPLAY_HEADER] = "true"
    return order


@router.get("/orders", response_model=Page[OrderListItem], tags=["orders"])
def list_orders(
    status_filter: list[OrderStatus] | None = Query(None, alias="status"),
    payment_status: PaymentStatus | None = None,
    order_type: OrderType | None = None,
    table_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    search: str | None = Query(None, max_length=50),
    params: PageParams = Depends(),
    ctx: RestaurantContext = Depends(require(Permission.ORDERS_READ)),
    db: Session = Depends(get_db),
) -> Page[OrderListItem]:
    items, total = order_service.list_orders(
        db,
        ctx,
        params,
        status=status_filter,
        payment_status=payment_status,
        order_type=order_type,
        table_id=table_id,
        customer_id=customer_id,
        start=start,
        end=end,
        search=search,
    )
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)


@router.get("/orders/{order_id}", response_model=OrderOut, tags=["orders"])
def get_order(
    order_id: uuid.UUID,
    ctx: RestaurantContext = Depends(require(Permission.ORDERS_READ)),
    db: Session = Depends(get_db),
) -> OrderOut:
    return order_service.get_order_out(db, ctx, order_id)


@router.patch(
    "/orders/{order_id}",
    response_model=OrderOut,
    tags=["orders"],
    summary="Change items, notes, customer or discount (until payment starts)",
)
def update_order(
    order_id: uuid.UUID,
    data: OrderUpdate,
    ctx: RestaurantContext = Depends(require(Permission.ORDERS_CREATE)),
    db: Session = Depends(get_db),
) -> OrderOut:
    return order_service.update_order(db, ctx, order_id, data)


@router.post(
    "/orders/{order_id}/confirm",
    response_model=OrderOut,
    tags=["orders"],
    summary="Confirm a draft: sends it to the kitchen and deducts stock (idempotent)",
)
def confirm_order(
    order_id: uuid.UUID,
    ctx: RestaurantContext = Depends(require(Permission.ORDERS_CREATE)),
    db: Session = Depends(get_db),
) -> OrderOut:
    return order_service.confirm_order(db, ctx, order_id)


@router.post("/orders/{order_id}/status", response_model=OrderOut, tags=["orders"])
def change_status(
    order_id: uuid.UUID,
    data: StatusChange,
    ctx: RestaurantContext = Depends(require(Permission.ORDERS_READ)),
    db: Session = Depends(get_db),
) -> OrderOut:
    return order_service.change_status(db, ctx, order_id, data.status)


@router.post("/orders/{order_id}/cancel", response_model=CancelResult, tags=["orders"])
def cancel_order(
    order_id: uuid.UUID,
    data: CancelRequest,
    ctx: RestaurantContext = Depends(require(Permission.ORDERS_READ)),
    db: Session = Depends(get_db),
) -> CancelResult:
    order, restored = order_service.cancel_order(db, ctx, order_id, data)
    note = "Deducted ingredients were returned to stock." if restored else None
    return CancelResult(order=order, stock_restored=restored, note=note)


@router.post(
    "/orders/{order_id}/payments",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    tags=["payments"],
    summary="Record a payment (send an Idempotency-Key to avoid duplicates)",
)
def record_payment(
    order_id: uuid.UUID,
    data: PaymentCreate,
    response: Response,
    key: str | None = Depends(_idempotency_key),
    ctx: RestaurantContext = Depends(require(Permission.PAYMENTS_RECORD)),
    db: Session = Depends(get_db),
) -> OrderOut:
    order, _, replayed = order_service.record_payment(db, ctx, order_id, data, key)
    if replayed:
        response.status_code = status.HTTP_200_OK
        response.headers[REPLAY_HEADER] = "true"
    return order


@router.get("/orders/{order_id}/payments", response_model=list[PaymentOut], tags=["payments"])
def list_order_payments(
    order_id: uuid.UUID,
    ctx: RestaurantContext = Depends(require(Permission.ORDERS_READ)),
    db: Session = Depends(get_db),
) -> list[PaymentOut]:
    order = order_service.load_order(db, ctx, order_id)
    return [order_service.payment_out(p) for p in order.payments]


@router.post(
    "/orders/{order_id}/refunds",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    tags=["payments"],
    summary="Record a refund against a payment (manager)",
)
def record_refund(
    order_id: uuid.UUID,
    data: RefundCreate,
    response: Response,
    key: str | None = Depends(_idempotency_key),
    ctx: RestaurantContext = Depends(require(Permission.REFUNDS_RECORD)),
    db: Session = Depends(get_db),
) -> OrderOut:
    order, _, replayed = order_service.record_refund(db, ctx, order_id, data, key)
    if replayed:
        response.status_code = status.HTTP_200_OK
        response.headers[REPLAY_HEADER] = "true"
    return order


@router.get("/orders/{order_id}/receipt", response_model=Receipt, tags=["orders"])
def receipt(
    order_id: uuid.UUID,
    ctx: RestaurantContext = Depends(require(Permission.ORDERS_READ)),
    db: Session = Depends(get_db),
) -> Receipt:
    return build_receipt(db, ctx, order_id)


@router.get("/payments", response_model=Page[PaymentOut], tags=["payments"])
def list_payments(
    start: datetime | None = None,
    end: datetime | None = None,
    method_code: str | None = None,
    params: PageParams = Depends(),
    ctx: RestaurantContext = Depends(require(Permission.ANALYTICS_READ)),
    db: Session = Depends(get_db),
) -> Page[PaymentOut]:
    stmt = scoped(Payment, ctx.restaurant_id).order_by(Payment.created_at.desc())
    if start:
        stmt = stmt.where(Payment.created_at >= start)
    if end:
        stmt = stmt.where(Payment.created_at < end)
    if method_code:
        stmt = stmt.where(Payment.method_code == method_code)
    items, total = paginate(db, stmt, params)
    return Page(
        items=[order_service.payment_out(p) for p in items], total=total, page=params.page, page_size=params.page_size
    )


@router.get("/kitchen/orders", response_model=list[KitchenTicket], tags=["kitchen"])
def kitchen_orders(
    status_filter: list[str] | None = Query(None, alias="status"),
    completed_hours: int = Query(12, ge=1, le=72),
    ctx: RestaurantContext = Depends(require(Permission.KITCHEN_READ)),
    db: Session = Depends(get_db),
) -> list[KitchenTicket]:
    return kitchen_service.list_tickets(db, ctx, status_filter, completed_hours)


@router.post("/kitchen/orders/{order_id}/status", response_model=KitchenTicket, tags=["kitchen"])
def kitchen_update(
    order_id: uuid.UUID,
    data: KitchenStatusChange,
    ctx: RestaurantContext = Depends(require(Permission.KITCHEN_READ)),
    db: Session = Depends(get_db),
) -> KitchenTicket:
    if not ctx.can(Permission.KITCHEN_UPDATE) and not (
        data.status == "COMPLETED" and ctx.can(Permission.ORDERS_COMPLETE)
    ):
        raise Forbidden("You cannot update kitchen orders.")
    return kitchen_service.update_ticket(db, ctx, order_id, data.status)
