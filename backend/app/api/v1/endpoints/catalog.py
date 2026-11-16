"""Categories, products and modifiers."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import RestaurantContext, require
from app.core.permissions import Permission
from app.db.session import get_db
from app.schemas.catalog import (
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
    ModifierGroupCreate,
    ModifierGroupOut,
    ModifierGroupUpdate,
    ModifierOptionCreate,
    ModifierOptionOut,
    ModifierOptionUpdate,
    ProductCreate,
    ProductModifierGroupsUpdate,
    ProductOut,
    ProductSuggestion,
    ProductUpdate,
)
from app.schemas.common import Message
from app.services import catalog, suggestions

router = APIRouter()
read = require(Permission.MENU_READ)
write = require(Permission.MENU_WRITE)


@router.get("/categories", response_model=list[CategoryOut], tags=["categories"])
def list_categories(
    include_inactive: bool = False, ctx: RestaurantContext = Depends(read), db: Session = Depends(get_db)
) -> list[CategoryOut]:
    return catalog.list_categories(db, ctx, include_inactive and ctx.can(Permission.MENU_WRITE))


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED, tags=["categories"])
def create_category(
    data: CategoryCreate, ctx: RestaurantContext = Depends(write), db: Session = Depends(get_db)
) -> CategoryOut:
    return catalog.create_category(db, ctx, data)


@router.patch("/categories/{category_id}", response_model=CategoryOut, tags=["categories"])
def update_category(
    category_id: uuid.UUID, data: CategoryUpdate, ctx: RestaurantContext = Depends(write), db: Session = Depends(get_db)
) -> CategoryOut:
    return catalog.update_category(db, ctx, category_id, data)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["categories"])
def delete_category(
    category_id: uuid.UUID, ctx: RestaurantContext = Depends(write), db: Session = Depends(get_db)
) -> Response:
    catalog.delete_category(db, ctx, category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/products", response_model=list[ProductOut], tags=["products"])
def list_products(
    category_id: uuid.UUID | None = None,
    search: str | None = Query(None, max_length=100),
    available_only: bool = False,
    include_inactive: bool = False,
    ctx: RestaurantContext = Depends(read),
    db: Session = Depends(get_db),
) -> list[ProductOut]:
    return catalog.list_products(
        db,
        ctx,
        category_id=category_id,
        search=search,
        available_only=available_only,
        include_inactive=include_inactive and ctx.can(Permission.MENU_WRITE),
    )


@router.get(
    "/products/suggestions",
    response_model=list[ProductSuggestion],
    tags=["products"],
    summary="Add-on suggestions for a POS cart, from this restaurant's sales",
)
def product_suggestions(
    product_id: list[uuid.UUID] = Query(default_factory=list, max_length=50, description="Products in the cart"),
    customer_id: uuid.UUID | None = None,
    limit: int = Query(4, ge=1, le=10),
    ctx: RestaurantContext = Depends(require(Permission.ORDERS_CREATE)),
    db: Session = Depends(get_db),
) -> list[ProductSuggestion]:
    return suggestions.suggest(db, ctx, product_id, customer_id, limit)


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED, tags=["products"])
def create_product(
    data: ProductCreate, ctx: RestaurantContext = Depends(write), db: Session = Depends(get_db)
) -> ProductOut:
    return catalog.create_product(db, ctx, data)


@router.get("/products/{product_id}", response_model=ProductOut, tags=["products"])
def get_product(
    product_id: uuid.UUID, ctx: RestaurantContext = Depends(read), db: Session = Depends(get_db)
) -> ProductOut:
    return catalog.get_product_out(db, ctx, product_id)


@router.patch("/products/{product_id}", response_model=ProductOut, tags=["products"])
def update_product(
    product_id: uuid.UUID, data: ProductUpdate, ctx: RestaurantContext = Depends(write), db: Session = Depends(get_db)
) -> ProductOut:
    return catalog.update_product(db, ctx, product_id, data)


@router.put("/products/{product_id}/modifier-groups", response_model=ProductOut, tags=["products"])
def set_modifier_groups(
    product_id: uuid.UUID,
    data: ProductModifierGroupsUpdate,
    ctx: RestaurantContext = Depends(write),
    db: Session = Depends(get_db),
) -> ProductOut:
    return catalog.set_product_modifier_groups(db, ctx, product_id, data.modifier_group_ids)


@router.delete(
    "/products/{product_id}",
    response_model=Message,
    tags=["products"],
    summary="Delete a never-sold product, or archive a product with sales history",
)
def delete_product(
    product_id: uuid.UUID, ctx: RestaurantContext = Depends(write), db: Session = Depends(get_db)
) -> Message:
    outcome = catalog.archive_or_delete_product(db, ctx, product_id)
    return Message(message=f"Product {outcome}.")


@router.get("/modifiers/groups", response_model=list[ModifierGroupOut], tags=["modifiers"])
def list_groups(
    include_inactive: bool = False, ctx: RestaurantContext = Depends(read), db: Session = Depends(get_db)
) -> list[ModifierGroupOut]:
    return catalog.list_modifier_groups(db, ctx, include_inactive and ctx.can(Permission.MENU_WRITE))


@router.post(
    "/modifiers/groups", response_model=ModifierGroupOut, status_code=status.HTTP_201_CREATED, tags=["modifiers"]
)
def create_group(
    data: ModifierGroupCreate, ctx: RestaurantContext = Depends(write), db: Session = Depends(get_db)
) -> ModifierGroupOut:
    return catalog.create_modifier_group(db, ctx, data)


@router.patch("/modifiers/groups/{group_id}", response_model=ModifierGroupOut, tags=["modifiers"])
def update_group(
    group_id: uuid.UUID,
    data: ModifierGroupUpdate,
    ctx: RestaurantContext = Depends(write),
    db: Session = Depends(get_db),
) -> ModifierGroupOut:
    return catalog.update_modifier_group(db, ctx, group_id, data)


@router.post(
    "/modifiers/groups/{group_id}/options",
    response_model=ModifierGroupOut,
    status_code=status.HTTP_201_CREATED,
    tags=["modifiers"],
)
def add_option(
    group_id: uuid.UUID,
    data: ModifierOptionCreate,
    ctx: RestaurantContext = Depends(write),
    db: Session = Depends(get_db),
) -> ModifierGroupOut:
    return catalog.add_modifier_option(db, ctx, group_id, data)


@router.patch("/modifiers/options/{option_id}", response_model=ModifierOptionOut, tags=["modifiers"])
def update_option(
    option_id: uuid.UUID,
    data: ModifierOptionUpdate,
    ctx: RestaurantContext = Depends(write),
    db: Session = Depends(get_db),
) -> ModifierOptionOut:
    return catalog.update_modifier_option(db, ctx, option_id, data)
