"""Customer profiles. Total spending is derived from eligible transactions."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import RestaurantContext
from app.core.errors import Conflict, ValidationFailed
from app.core.permissions import Permission
from app.models import Customer, LoyaltyTransaction, Order, OrderItem, Product
from app.models.enums import LoyaltyTransactionType, OrderStatus, PaymentStatus
from app.repositories.tenant import get_owned, scoped
from app.schemas.common import PageParams, paginate
from app.schemas.customers import (
    CustomerCreate,
    CustomerFavourite,
    CustomerLookup,
    CustomerOut,
    CustomerUpdate,
    LoyaltyAdjust,
)
from app.services import loyalty, realtime
from app.services.audit import record_audit

SETTLED = (PaymentStatus.PAID, PaymentStatus.PARTIALLY_REFUNDED, PaymentStatus.REFUNDED)


def normalise_phone(phone: str | None) -> str | None:
    if phone is None:
        return None
    phone = phone.strip()
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 6:
        raise ValidationFailed("Phone number is too short.")
    return ("+" if phone.startswith("+") else "") + digits


def mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    return "•" * max(len(phone) - 4, 0) + phone[-4:]


def lookup_out(customer: Customer) -> CustomerLookup:
    return CustomerLookup(
        id=customer.id,
        name=customer.name,
        phone_masked=mask_phone(customer.phone),
        loyalty_balance=customer.loyalty_balance,
    )


def _stats(db: Session, restaurant_id: uuid.UUID, ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int, object]]:
    if not ids:
        return {}
    rows = db.execute(
        select(
            Order.customer_id,
            func.count(),
            func.coalesce(func.sum(Order.total_minor - Order.amount_refunded_minor), 0),
            func.max(Order.paid_at),
        )
        .where(
            Order.restaurant_id == restaurant_id,
            Order.customer_id.in_(ids),
            Order.status != OrderStatus.CANCELLED,
            Order.payment_status.in_(SETTLED),
        )
        .group_by(Order.customer_id)
    ).all()
    return {cid: (int(count), int(spent), last) for cid, count, spent, last in rows}


def full_out(customer: Customer, stats: tuple[int, int, object] | None) -> CustomerOut:
    out = CustomerOut.model_validate(customer)
    if stats:
        out.order_count, out.total_spent_minor, out.last_order_at = stats  # type: ignore[assignment]
    return out


def list_customers(
    db: Session, ctx: RestaurantContext, params: PageParams, search: str | None
) -> tuple[list[CustomerOut] | list[CustomerLookup], int]:
    stmt = scoped(Customer, ctx.restaurant_id).order_by(Customer.name)
    if search:
        term = search.strip()
        conditions = [Customer.name.ilike(f"%{term}%")]
        digits = re.sub(r"\D", "", term)
        if len(digits) >= 3:
            conditions.append(Customer.phone.contains(digits))
        stmt = stmt.where(or_(*conditions))
    items, total = paginate(db, stmt, params)
    if not ctx.can(Permission.CUSTOMERS_WRITE):
        return [lookup_out(c) for c in items], total
    stats = _stats(db, ctx.restaurant_id, [c.id for c in items])
    return [full_out(c, stats.get(c.id)) for c in items], total


def get_customer(db: Session, ctx: RestaurantContext, customer_id: uuid.UUID) -> CustomerOut | CustomerLookup:
    customer = get_owned(db, Customer, customer_id, ctx.restaurant_id, "Customer")
    if not ctx.can(Permission.CUSTOMERS_WRITE):
        return lookup_out(customer)
    return full_out(customer, _stats(db, ctx.restaurant_id, [customer.id]).get(customer.id))


def _unique_phone(db: Session, ctx: RestaurantContext, phone: str | None, exclude: uuid.UUID | None = None) -> None:
    if not phone:
        return
    stmt = scoped(Customer, ctx.restaurant_id).where(Customer.phone == phone)
    if exclude:
        stmt = stmt.where(Customer.id != exclude)
    if db.scalar(stmt):
        raise Conflict("A customer with this phone number already exists.", code="phone_taken")


def create_customer(db: Session, ctx: RestaurantContext, data: CustomerCreate) -> CustomerOut | CustomerLookup:
    phone = normalise_phone(data.phone)
    _unique_phone(db, ctx, phone)
    customer = Customer(
        restaurant_id=ctx.restaurant_id,
        name=data.name,
        phone=phone,
        email=data.email.lower() if data.email else None,
        notes=data.notes,
    )
    db.add(customer)
    realtime.emit(db, ctx.restaurant_id, "customer.changed", actor_user_id=ctx.user_id)
    db.commit()
    return full_out(customer, None) if ctx.can(Permission.CUSTOMERS_WRITE) else lookup_out(customer)


def update_customer(db: Session, ctx: RestaurantContext, customer_id: uuid.UUID, data: CustomerUpdate) -> CustomerOut:
    customer = get_owned(db, Customer, customer_id, ctx.restaurant_id, "Customer")
    changes = data.model_dump(exclude_unset=True)
    if "phone" in changes:
        changes["phone"] = normalise_phone(changes["phone"])
        _unique_phone(db, ctx, changes["phone"], exclude=customer.id)
    if changes.get("email"):
        changes["email"] = changes["email"].lower()
    for field, value in changes.items():
        if value is not None or field in {"phone", "email", "notes"}:
            setattr(customer, field, value)
    realtime.emit(db, ctx.restaurant_id, "customer.changed", actor_user_id=ctx.user_id)
    db.commit()
    return full_out(customer, _stats(db, ctx.restaurant_id, [customer.id]).get(customer.id))


def anonymise_customer(db: Session, ctx: RestaurantContext, customer_id: uuid.UUID) -> CustomerOut:
    """Remove personal data but keep the record so order history and the
    loyalty ledger stay consistent."""
    customer = get_owned(db, Customer, customer_id, ctx.restaurant_id, "Customer")
    customer.name = "Deleted customer"
    customer.phone = None
    customer.email = None
    customer.notes = None
    record_audit(
        db,
        action="customer.anonymised",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="customer",
        entity_id=customer.id,
        ip_address=ctx.ip,
    )
    realtime.emit(db, ctx.restaurant_id, "customer.changed", actor_user_id=ctx.user_id)
    db.commit()
    return full_out(customer, None)


def list_transactions(
    db: Session, ctx: RestaurantContext, customer_id: uuid.UUID, params: PageParams
) -> tuple[list[LoyaltyTransaction], int]:
    customer = get_owned(db, Customer, customer_id, ctx.restaurant_id, "Customer")
    stmt = (
        select(LoyaltyTransaction)
        .where(LoyaltyTransaction.customer_id == customer.id)
        .order_by(LoyaltyTransaction.created_at.desc())
    )
    return paginate(db, stmt, params)


def adjust_points(db: Session, ctx: RestaurantContext, customer_id: uuid.UUID, data: LoyaltyAdjust) -> CustomerOut:
    if data.points == 0:
        raise ValidationFailed("Adjustment must not be zero.")
    get_owned(db, Customer, customer_id, ctx.restaurant_id, "Customer")
    customer = loyalty.lock_customer(db, ctx.restaurant_id, customer_id)
    loyalty.post(
        db, customer, LoyaltyTransactionType.ADJUST, data.points, reason=data.reason, actor_user_id=ctx.user_id
    )
    record_audit(
        db,
        action="loyalty.adjusted",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="customer",
        entity_id=customer.id,
        details={"points": data.points, "reason": data.reason},
        ip_address=ctx.ip,
    )
    realtime.emit(db, ctx.restaurant_id, "customer.changed", actor_user_id=ctx.user_id)
    db.commit()
    return full_out(customer, _stats(db, ctx.restaurant_id, [customer.id]).get(customer.id))


def favourites(db: Session, ctx: RestaurantContext, customer_id: uuid.UUID, limit: int = 5) -> list[CustomerFavourite]:
    """What this customer orders most often (by number of paid orders, then quantity)."""
    get_owned(db, Customer, customer_id, ctx.restaurant_id, "Customer")
    visits = func.count(func.distinct(Order.id))
    rows = db.execute(
        select(OrderItem.product_id, Product.name, visits, func.sum(OrderItem.quantity), func.max(Order.paid_at))
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(
            Order.restaurant_id == ctx.restaurant_id,
            Order.customer_id == customer_id,
            Order.status != OrderStatus.CANCELLED,
            Order.payment_status.in_((PaymentStatus.PAID, PaymentStatus.PARTIALLY_REFUNDED)),
        )
        .group_by(OrderItem.product_id, Product.name)
        .order_by(visits.desc(), func.sum(OrderItem.quantity).desc(), Product.name)
        .limit(limit)
    ).all()
    return [
        CustomerFavourite(product_id=pid, product_name=name, orders=n, quantity=int(qty), last_ordered_at=last)
        for pid, name, n, qty, last in rows
    ]
