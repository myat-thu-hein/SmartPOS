"""Restaurants, restaurant settings, payment methods, discounts and audit logs."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, RestaurantContext, get_auth, require, require_platform_admin
from app.core.errors import Conflict, NotFound
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import AuditLog, Restaurant, RestaurantMembership, User
from app.schemas.auth import MemberAdd
from app.schemas.common import Message, Page, PageParams, paginate
from app.schemas.restaurants import (
    AuditLogOut,
    DiscountCreate,
    DiscountOut,
    DiscountUpdate,
    PaymentMethodCreate,
    PaymentMethodOut,
    PaymentMethodUpdate,
    RestaurantCreate,
    RestaurantOut,
    RestaurantSettingsUpdate,
    RestaurantSummary,
)
from app.services import restaurants as restaurant_service
from app.services.audit import record_audit
from app.services.auth import get_user_by_email
from app.services.users import memberships_for

router = APIRouter(tags=["restaurants"])


@router.get("/restaurants", response_model=list[RestaurantSummary], summary="Restaurants the user can access")
def list_restaurants(auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> list[RestaurantSummary]:
    ids = {m.restaurant_id for m in memberships_for(db, auth.user)}
    if not ids:
        return []
    rows = db.scalars(select(Restaurant).where(Restaurant.id.in_(ids)).order_by(Restaurant.name)).all()
    return [RestaurantSummary.model_validate(r) for r in rows]


@router.post("/restaurants", response_model=RestaurantOut, status_code=status.HTTP_201_CREATED)
def create_restaurant(
    data: RestaurantCreate, auth: AuthContext = Depends(require_platform_admin), db: Session = Depends(get_db)
) -> RestaurantOut:
    restaurant = restaurant_service.create_restaurant(db, data, auth.user, None)
    return RestaurantOut.model_validate(restaurant)


@router.get("/restaurants/current", response_model=RestaurantOut)
def get_current_restaurant(
    ctx: RestaurantContext = Depends(require(Permission.MENU_READ)), db: Session = Depends(get_db)
) -> RestaurantOut:
    return RestaurantOut.model_validate(ctx.restaurant)


@router.patch("/restaurants/current", response_model=RestaurantOut)
def update_current_restaurant(
    data: RestaurantSettingsUpdate,
    ctx: RestaurantContext = Depends(require(Permission.SETTINGS_WRITE)),
    db: Session = Depends(get_db),
) -> RestaurantOut:
    return RestaurantOut.model_validate(restaurant_service.update_settings(db, ctx, data))


@router.patch(
    "/restaurants/{restaurant_id}/status",
    response_model=RestaurantOut,
    summary="Activate or deactivate a restaurant (admin)",
)
def set_restaurant_status(
    restaurant_id: uuid.UUID,
    is_active: bool = Query(...),
    auth: AuthContext = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> RestaurantOut:
    restaurant = db.get(Restaurant, restaurant_id)
    if restaurant is None:
        raise NotFound("Restaurant not found.")
    restaurant.is_active = is_active
    record_audit(
        db,
        action="restaurant.status_changed",
        actor_user_id=auth.user.id,
        restaurant_id=restaurant.id,
        entity_type="restaurant",
        entity_id=restaurant.id,
        details={"is_active": is_active},
    )
    db.commit()
    return RestaurantOut.model_validate(restaurant)


@router.post(
    "/restaurants/{restaurant_id}/members",
    response_model=Message,
    status_code=status.HTTP_201_CREATED,
    summary="Add an existing user to a restaurant (admin)",
)
def add_member(
    restaurant_id: uuid.UUID,
    data: MemberAdd,
    auth: AuthContext = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> Message:
    restaurant = db.get(Restaurant, restaurant_id)
    if restaurant is None:
        raise NotFound("Restaurant not found.")
    user = get_user_by_email(db, data.email)
    if user is None:
        raise NotFound("No user exists with this email.")
    existing = db.scalar(
        select(RestaurantMembership).where(
            RestaurantMembership.restaurant_id == restaurant_id, RestaurantMembership.user_id == user.id
        )
    )
    if existing and existing.is_active:
        raise Conflict("This user is already a member of the restaurant.")
    if existing:
        existing.is_active = True
        existing.role = data.role
    else:
        db.add(RestaurantMembership(restaurant_id=restaurant_id, user_id=user.id, role=data.role))
    record_audit(
        db,
        action="membership.added",
        actor_user_id=auth.user.id,
        restaurant_id=restaurant_id,
        entity_type="user",
        entity_id=user.id,
        details={"role": data.role.value},
    )
    db.commit()
    return Message(message="Member added.")


@router.get("/payments/methods", response_model=list[PaymentMethodOut], tags=["payments"])
def list_payment_methods(
    include_inactive: bool = False,
    ctx: RestaurantContext = Depends(require(Permission.SETTINGS_READ)),
    db: Session = Depends(get_db),
) -> list[PaymentMethodOut]:
    return [
        PaymentMethodOut.model_validate(m) for m in restaurant_service.list_payment_methods(db, ctx, include_inactive)
    ]


@router.post(
    "/payments/methods", response_model=PaymentMethodOut, status_code=status.HTTP_201_CREATED, tags=["payments"]
)
def create_payment_method(
    data: PaymentMethodCreate,
    ctx: RestaurantContext = Depends(require(Permission.SETTINGS_WRITE)),
    db: Session = Depends(get_db),
) -> PaymentMethodOut:
    return PaymentMethodOut.model_validate(restaurant_service.create_payment_method(db, ctx, data))


@router.patch("/payments/methods/{method_id}", response_model=PaymentMethodOut, tags=["payments"])
def update_payment_method(
    method_id: uuid.UUID,
    data: PaymentMethodUpdate,
    ctx: RestaurantContext = Depends(require(Permission.SETTINGS_WRITE)),
    db: Session = Depends(get_db),
) -> PaymentMethodOut:
    return PaymentMethodOut.model_validate(restaurant_service.update_payment_method(db, ctx, method_id, data))


@router.get("/discounts", response_model=list[DiscountOut], tags=["discounts"])
def list_discounts(
    include_inactive: bool = False,
    ctx: RestaurantContext = Depends(require(Permission.DISCOUNTS_APPLY)),
    db: Session = Depends(get_db),
) -> list[DiscountOut]:
    return [DiscountOut.model_validate(d) for d in restaurant_service.list_discounts(db, ctx, include_inactive)]


@router.post("/discounts", response_model=DiscountOut, status_code=status.HTTP_201_CREATED, tags=["discounts"])
def create_discount(
    data: DiscountCreate,
    ctx: RestaurantContext = Depends(require(Permission.SETTINGS_WRITE)),
    db: Session = Depends(get_db),
) -> DiscountOut:
    return DiscountOut.model_validate(restaurant_service.create_discount(db, ctx, data))


@router.patch("/discounts/{discount_id}", response_model=DiscountOut, tags=["discounts"])
def update_discount(
    discount_id: uuid.UUID,
    data: DiscountUpdate,
    ctx: RestaurantContext = Depends(require(Permission.SETTINGS_WRITE)),
    db: Session = Depends(get_db),
) -> DiscountOut:
    return DiscountOut.model_validate(restaurant_service.update_discount(db, ctx, discount_id, data))


@router.get("/audit-logs", response_model=Page[AuditLogOut], tags=["audit"], summary="Audit trail (admin)")
def list_audit_logs(
    restaurant_id: uuid.UUID | None = None,
    action: str | None = Query(None, max_length=100),
    start: datetime | None = None,
    end: datetime | None = None,
    params: PageParams = Depends(),
    _: AuthContext = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> Page[AuditLogOut]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if restaurant_id:
        stmt = stmt.where(AuditLog.restaurant_id == restaurant_id)
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"{action}%"))
    if start:
        stmt = stmt.where(AuditLog.created_at >= start)
    if end:
        stmt = stmt.where(AuditLog.created_at < end)
    items, total = paginate(db, stmt, params)
    emails = (
        dict(
            db.execute(
                select(User.id, User.email).where(User.id.in_({i.actor_user_id for i in items if i.actor_user_id}))
            ).all()
        )
        if items
        else {}
    )
    out = []
    for item in items:
        row = AuditLogOut.model_validate(item)
        row.actor_email = emails.get(item.actor_user_id)
        out.append(row)
    return Page(items=out, total=total, page=params.page, page_size=params.page_size)
