"""Restaurant (tenant) setup and configuration."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.api.deps import RestaurantContext
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.models import Discount, PaymentMethod, Restaurant, RestaurantCounter, RestaurantMembership, User
from app.models.enums import PaymentMethodKind, RestaurantRole
from app.schemas.restaurants import (
    DiscountCreate,
    DiscountUpdate,
    PaymentMethodCreate,
    PaymentMethodUpdate,
    RestaurantCreate,
    RestaurantSettingsUpdate,
)
from app.services import realtime
from app.services.audit import record_audit
from app.services.auth import get_user_by_email

DEFAULT_PAYMENT_METHODS = (
    ("CASH", "Cash", PaymentMethodKind.CASH),
    ("CARD", "Card (external terminal)", PaymentMethodKind.CARD),
    ("QR", "QR PromptPay (simulated)", PaymentMethodKind.QR),
)

# Settings whose change affects money or stock and is therefore audited in detail.
SENSITIVE_SETTINGS = {
    "tax_rate_bps",
    "prices_include_tax",
    "service_charge_bps",
    "service_charge_taxable",
    "service_charge_dine_in_only",
    "max_cashier_discount_bps",
    "allow_negative_stock",
    "loyalty_enabled",
    "loyalty_spend_per_point_minor",
    "loyalty_point_value_minor",
}


def next_counter(db: Session, restaurant_id: uuid.UUID, name: str) -> int:
    """Atomically allocate the next number of a per-restaurant sequence.

    The upsert takes a row lock on the counter until the surrounding
    transaction ends, so numbers are unique and gap-free per restaurant.
    """
    stmt = (
        pg_insert(RestaurantCounter)
        .values(restaurant_id=restaurant_id, name=name, value=1)
        .on_conflict_do_update(
            index_elements=[RestaurantCounter.restaurant_id, RestaurantCounter.name],
            set_={"value": RestaurantCounter.__table__.c.value + 1},
        )
        .returning(RestaurantCounter.value)
    )
    return int(db.execute(stmt).scalar_one())


def create_restaurant(db: Session, data: RestaurantCreate, actor: User, ip: str | None) -> Restaurant:
    restaurant = Restaurant(
        name=data.name, branch_name=data.branch_name, timezone=data.timezone, currency=data.currency
    )
    db.add(restaurant)
    db.flush()
    initialise_restaurant_defaults(db, restaurant)
    if data.manager_email:
        manager = get_user_by_email(db, data.manager_email)
        if manager is None:
            raise NotFound("No user exists with that manager email. Create the user first.")
        db.add(RestaurantMembership(restaurant_id=restaurant.id, user_id=manager.id, role=RestaurantRole.MANAGER))
    record_audit(
        db,
        action="restaurant.created",
        actor_user_id=actor.id,
        restaurant_id=restaurant.id,
        entity_type="restaurant",
        entity_id=restaurant.id,
        ip_address=ip,
    )
    db.commit()
    return restaurant


def initialise_restaurant_defaults(db: Session, restaurant: Restaurant) -> None:
    for index, (code, name, kind) in enumerate(DEFAULT_PAYMENT_METHODS):
        db.add(
            PaymentMethod(
                restaurant_id=restaurant.id, code=code, name=name, kind=kind, is_simulated=True, display_order=index
            )
        )
    db.flush()


def update_settings(db: Session, ctx: RestaurantContext, data: RestaurantSettingsUpdate) -> Restaurant:
    restaurant = ctx.restaurant
    changes: dict[str, object] = {}
    for field, value in data.model_dump(exclude_unset=True).items():
        if getattr(restaurant, field) != value:
            changes[field] = {"from": getattr(restaurant, field), "to": value} if field in SENSITIVE_SETTINGS else True
            setattr(restaurant, field, value)
    if changes:
        record_audit(
            db,
            action="restaurant.settings_updated",
            actor_user_id=ctx.user_id,
            restaurant_id=ctx.restaurant_id,
            entity_type="restaurant",
            entity_id=restaurant.id,
            details=changes,
            ip_address=ctx.ip,
        )
    realtime.emit(db, ctx.restaurant_id, "settings.changed", actor_user_id=ctx.user_id)
    db.commit()
    return restaurant


def list_payment_methods(db: Session, ctx: RestaurantContext, include_inactive: bool) -> list[PaymentMethod]:
    stmt = select(PaymentMethod).where(PaymentMethod.restaurant_id == ctx.restaurant_id)
    if not include_inactive:
        stmt = stmt.where(PaymentMethod.is_active.is_(True))
    return list(db.scalars(stmt.order_by(PaymentMethod.display_order, PaymentMethod.name)).all())


def get_payment_method(db: Session, ctx: RestaurantContext, method_id: uuid.UUID) -> PaymentMethod:
    method = db.scalar(
        select(PaymentMethod).where(PaymentMethod.id == method_id, PaymentMethod.restaurant_id == ctx.restaurant_id)
    )
    if method is None:
        raise NotFound("Payment method not found.")
    return method


def create_payment_method(db: Session, ctx: RestaurantContext, data: PaymentMethodCreate) -> PaymentMethod:
    exists = db.scalar(
        select(PaymentMethod.id).where(
            PaymentMethod.restaurant_id == ctx.restaurant_id, PaymentMethod.code == data.code
        )
    )
    if exists:
        raise Conflict("A payment method with this code already exists.")
    # No payment provider integration exists yet, so every method is a local record.
    method = PaymentMethod(
        restaurant_id=ctx.restaurant_id,
        code=data.code,
        name=data.name,
        kind=data.kind,
        display_order=data.display_order,
        is_simulated=True,
    )
    db.add(method)
    record_audit(
        db,
        action="payment_method.created",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="payment_method",
        details={"code": data.code},
        ip_address=ctx.ip,
    )
    realtime.emit(db, ctx.restaurant_id, "settings.changed", actor_user_id=ctx.user_id)
    db.commit()
    return method


def update_payment_method(
    db: Session, ctx: RestaurantContext, method_id: uuid.UUID, data: PaymentMethodUpdate
) -> PaymentMethod:
    method = get_payment_method(db, ctx, method_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(method, field, value)
    realtime.emit(db, ctx.restaurant_id, "settings.changed", actor_user_id=ctx.user_id)
    db.commit()
    return method


def list_discounts(db: Session, ctx: RestaurantContext, include_inactive: bool) -> list[Discount]:
    stmt = select(Discount).where(Discount.restaurant_id == ctx.restaurant_id)
    if not include_inactive:
        stmt = stmt.where(Discount.is_active.is_(True))
    return list(db.scalars(stmt.order_by(Discount.name)).all())


def get_discount(db: Session, ctx: RestaurantContext, discount_id: uuid.UUID) -> Discount:
    discount = db.scalar(
        select(Discount).where(Discount.id == discount_id, Discount.restaurant_id == ctx.restaurant_id)
    )
    if discount is None:
        raise NotFound("Discount not found.")
    return discount


def create_discount(db: Session, ctx: RestaurantContext, data: DiscountCreate) -> Discount:
    exists = db.scalar(
        select(Discount.id).where(Discount.restaurant_id == ctx.restaurant_id, Discount.name == data.name)
    )
    if exists:
        raise Conflict("A discount with this name already exists.")
    discount = Discount(restaurant_id=ctx.restaurant_id, **data.model_dump())
    db.add(discount)
    record_audit(
        db,
        action="discount.created",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="discount",
        details=data.model_dump(mode="json"),
        ip_address=ctx.ip,
    )
    realtime.emit(db, ctx.restaurant_id, "settings.changed", actor_user_id=ctx.user_id)
    db.commit()
    return discount


def update_discount(db: Session, ctx: RestaurantContext, discount_id: uuid.UUID, data: DiscountUpdate) -> Discount:
    discount = get_discount(db, ctx, discount_id)
    changes = data.model_dump(exclude_unset=True)
    if "value" in changes and discount.kind.value == "PERCENT" and changes["value"] > 10000:
        raise ValidationFailed("Percentage discounts cannot exceed 10000 basis points (100%).")
    for field, value in changes.items():
        setattr(discount, field, value)
    record_audit(
        db,
        action="discount.updated",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="discount",
        entity_id=discount.id,
        details=changes,
        ip_address=ctx.ip,
    )
    realtime.emit(db, ctx.restaurant_id, "settings.changed", actor_user_id=ctx.user_id)
    db.commit()
    return discount
