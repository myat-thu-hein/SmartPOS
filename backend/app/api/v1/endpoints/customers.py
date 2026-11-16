"""Customers and loyalty."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import RestaurantContext, require
from app.core.permissions import Permission
from app.db.session import get_db
from app.schemas.common import Page, PageParams
from app.schemas.customers import (
    CustomerCreate,
    CustomerFavourite,
    CustomerLookup,
    CustomerOut,
    CustomerUpdate,
    LoyaltyAdjust,
    LoyaltySettingsOut,
    LoyaltyTransactionOut,
)
from app.schemas.orders import OrderListItem
from app.services import customers as customer_service
from app.services import orders as order_service

router = APIRouter()


@router.get(
    "/customers",
    response_model=Page[CustomerOut] | Page[CustomerLookup],
    tags=["customers"],
    summary="Search customers (cashiers receive masked contact details)",
)
def list_customers(
    search: str | None = Query(None, max_length=100),
    params: PageParams = Depends(),
    ctx: RestaurantContext = Depends(require(Permission.CUSTOMERS_READ)),
    db: Session = Depends(get_db),
):
    items, total = customer_service.list_customers(db, ctx, params, search)
    return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}


@router.post(
    "/customers", response_model=CustomerOut | CustomerLookup, status_code=status.HTTP_201_CREATED, tags=["customers"]
)
def create_customer(
    data: CustomerCreate,
    ctx: RestaurantContext = Depends(require(Permission.CUSTOMERS_CREATE)),
    db: Session = Depends(get_db),
):
    return customer_service.create_customer(db, ctx, data)


@router.get("/customers/{customer_id}", response_model=CustomerOut | CustomerLookup, tags=["customers"])
def get_customer(
    customer_id: uuid.UUID,
    ctx: RestaurantContext = Depends(require(Permission.CUSTOMERS_READ)),
    db: Session = Depends(get_db),
):
    return customer_service.get_customer(db, ctx, customer_id)


@router.patch("/customers/{customer_id}", response_model=CustomerOut, tags=["customers"])
def update_customer(
    customer_id: uuid.UUID,
    data: CustomerUpdate,
    ctx: RestaurantContext = Depends(require(Permission.CUSTOMERS_WRITE)),
    db: Session = Depends(get_db),
) -> CustomerOut:
    return customer_service.update_customer(db, ctx, customer_id, data)


@router.post(
    "/customers/{customer_id}/anonymise",
    response_model=CustomerOut,
    tags=["customers"],
    summary="Erase personal data while keeping order and loyalty history",
)
def anonymise_customer(
    customer_id: uuid.UUID,
    ctx: RestaurantContext = Depends(require(Permission.CUSTOMERS_WRITE)),
    db: Session = Depends(get_db),
) -> CustomerOut:
    return customer_service.anonymise_customer(db, ctx, customer_id)


@router.get("/customers/{customer_id}/orders", response_model=Page[OrderListItem], tags=["customers"])
def customer_orders(
    customer_id: uuid.UUID,
    params: PageParams = Depends(),
    ctx: RestaurantContext = Depends(require(Permission.CUSTOMERS_WRITE, Permission.ORDERS_READ)),
    db: Session = Depends(get_db),
) -> Page[OrderListItem]:
    customer_service.get_customer(db, ctx, customer_id)
    items, total = order_service.list_orders(
        db,
        ctx,
        params,
        status=None,
        payment_status=None,
        order_type=None,
        table_id=None,
        customer_id=customer_id,
        start=None,
        end=None,
        search=None,
    )
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)


@router.get("/customers/{customer_id}/favourites", response_model=list[CustomerFavourite], tags=["customers"])
def customer_favourites(
    customer_id: uuid.UUID,
    limit: int = Query(5, ge=1, le=20),
    ctx: RestaurantContext = Depends(require(Permission.CUSTOMERS_WRITE, Permission.ORDERS_READ)),
    db: Session = Depends(get_db),
) -> list[CustomerFavourite]:
    return customer_service.favourites(db, ctx, customer_id, limit)


@router.get("/loyalty/settings", response_model=LoyaltySettingsOut, tags=["loyalty"])
def loyalty_settings(ctx: RestaurantContext = Depends(require(Permission.CUSTOMERS_READ))) -> LoyaltySettingsOut:
    r = ctx.restaurant
    description = (
        f"Earn 1 point per {r.loyalty_spend_per_point_minor / 100:.2f} {r.currency} spent; "
        f"each point is worth {r.loyalty_point_value_minor / 100:.2f} {r.currency} when redeemed."
        if r.loyalty_enabled
        else "Loyalty programme is disabled."
    )
    return LoyaltySettingsOut(
        loyalty_enabled=r.loyalty_enabled,
        loyalty_spend_per_point_minor=r.loyalty_spend_per_point_minor,
        loyalty_point_value_minor=r.loyalty_point_value_minor,
        description=description,
    )


@router.get(
    "/loyalty/customers/{customer_id}/transactions", response_model=Page[LoyaltyTransactionOut], tags=["loyalty"]
)
def loyalty_transactions(
    customer_id: uuid.UUID,
    params: PageParams = Depends(),
    ctx: RestaurantContext = Depends(require(Permission.CUSTOMERS_WRITE)),
    db: Session = Depends(get_db),
) -> Page[LoyaltyTransactionOut]:
    items, total = customer_service.list_transactions(db, ctx, customer_id, params)
    return Page(
        items=[LoyaltyTransactionOut.model_validate(i) for i in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("/loyalty/customers/{customer_id}/adjust", response_model=CustomerOut, tags=["loyalty"])
def adjust_points(
    customer_id: uuid.UUID,
    data: LoyaltyAdjust,
    ctx: RestaurantContext = Depends(require(Permission.LOYALTY_ADJUST)),
    db: Session = Depends(get_db),
) -> CustomerOut:
    return customer_service.adjust_points(db, ctx, customer_id, data)
