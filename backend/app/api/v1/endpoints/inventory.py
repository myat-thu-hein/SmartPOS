"""Ingredients, recipes and inventory movements."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import RestaurantContext, require
from app.core.permissions import Permission
from app.db.session import get_db
from app.models.enums import MovementType
from app.schemas.analytics import StockRisk
from app.schemas.common import Page, PageParams
from app.schemas.inventory import (
    IngredientCreate,
    IngredientOut,
    IngredientUnitIn,
    IngredientUpdate,
    InventorySummary,
    MovementCreate,
    MovementOut,
    RecipeOut,
    RecipeSet,
    RecipeSummary,
    StockCountCreate,
)
from app.services import insights
from app.services import inventory as inventory_service
from app.services import recipes as recipe_service

router = APIRouter()
inv_read = require(Permission.INVENTORY_READ)
inv_write = require(Permission.INVENTORY_WRITE)


@router.get("/ingredients", response_model=list[IngredientOut], tags=["ingredients"])
def list_ingredients(
    search: str | None = Query(None, max_length=100),
    low_stock_only: bool = False,
    include_inactive: bool = False,
    ctx: RestaurantContext = Depends(inv_read),
    db: Session = Depends(get_db),
) -> list[IngredientOut]:
    return inventory_service.list_ingredients(
        db, ctx, search=search, low_stock_only=low_stock_only, include_inactive=include_inactive
    )


@router.post("/ingredients", response_model=IngredientOut, status_code=status.HTTP_201_CREATED, tags=["ingredients"])
def create_ingredient(
    data: IngredientCreate, ctx: RestaurantContext = Depends(inv_write), db: Session = Depends(get_db)
) -> IngredientOut:
    return inventory_service.create_ingredient(db, ctx, data)


@router.get("/ingredients/{ingredient_id}", response_model=IngredientOut, tags=["ingredients"])
def get_ingredient(
    ingredient_id: uuid.UUID, ctx: RestaurantContext = Depends(inv_read), db: Session = Depends(get_db)
) -> IngredientOut:
    return inventory_service.to_out(
        inventory_service.get_ingredient(db, ctx, ingredient_id),
        inventory_service.supplier_names(db, ctx.restaurant_id),
    )


@router.patch("/ingredients/{ingredient_id}", response_model=IngredientOut, tags=["ingredients"])
def update_ingredient(
    ingredient_id: uuid.UUID,
    data: IngredientUpdate,
    ctx: RestaurantContext = Depends(inv_write),
    db: Session = Depends(get_db),
) -> IngredientOut:
    return inventory_service.update_ingredient(db, ctx, ingredient_id, data)


@router.post(
    "/ingredients/{ingredient_id}/units",
    response_model=IngredientOut,
    status_code=status.HTTP_201_CREATED,
    tags=["ingredients"],
    summary="Define a pack unit such as 'tray' = 30 pieces",
)
def add_unit(
    ingredient_id: uuid.UUID,
    data: IngredientUnitIn,
    ctx: RestaurantContext = Depends(inv_write),
    db: Session = Depends(get_db),
) -> IngredientOut:
    return inventory_service.add_unit(db, ctx, ingredient_id, data)


@router.delete("/ingredients/{ingredient_id}/units/{unit_id}", response_model=IngredientOut, tags=["ingredients"])
def remove_unit(
    ingredient_id: uuid.UUID,
    unit_id: uuid.UUID,
    ctx: RestaurantContext = Depends(inv_write),
    db: Session = Depends(get_db),
) -> IngredientOut:
    return inventory_service.remove_unit(db, ctx, ingredient_id, unit_id)


@router.get("/inventory/summary", response_model=InventorySummary, tags=["inventory"])
def inventory_summary(ctx: RestaurantContext = Depends(inv_read), db: Session = Depends(get_db)) -> InventorySummary:
    return inventory_service.summary(db, ctx)


@router.get(
    "/inventory/stock-risk",
    response_model=list[StockRisk],
    tags=["inventory"],
    summary="Days of cover and stock-out risk per ingredient",
)
def stock_risk(ctx: RestaurantContext = Depends(inv_read), db: Session = Depends(get_db)) -> list[StockRisk]:
    return insights.stock_risks(db, ctx)


@router.get("/inventory/low-stock", response_model=list[IngredientOut], tags=["inventory"])
def low_stock(ctx: RestaurantContext = Depends(inv_read), db: Session = Depends(get_db)) -> list[IngredientOut]:
    return inventory_service.list_ingredients(db, ctx, search=None, low_stock_only=True, include_inactive=False)


@router.get("/inventory/movements", response_model=Page[MovementOut], tags=["inventory"])
def list_movements(
    ingredient_id: uuid.UUID | None = None,
    movement_type: MovementType | None = None,
    order_id: uuid.UUID | None = None,
    purchase_order_id: uuid.UUID | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    params: PageParams = Depends(),
    ctx: RestaurantContext = Depends(inv_read),
    db: Session = Depends(get_db),
) -> Page[MovementOut]:
    items, total = inventory_service.list_movements(
        db,
        ctx,
        params,
        ingredient_id=ingredient_id,
        movement_type=movement_type,
        order_id=order_id,
        purchase_order_id=purchase_order_id,
        start=start,
        end=end,
    )
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)


@router.post(
    "/inventory/movements",
    response_model=MovementOut,
    status_code=status.HTTP_201_CREATED,
    tags=["inventory"],
    summary="Record a stock receipt, issue, adjustment or waste",
)
def create_movement(
    data: MovementCreate, ctx: RestaurantContext = Depends(inv_write), db: Session = Depends(get_db)
) -> MovementOut:
    return inventory_service.record_manual_movement(db, ctx, data)


@router.post(
    "/inventory/stock-count",
    response_model=MovementOut | None,
    tags=["inventory"],
    summary="Record a physical count; posts an adjustment for the difference",
)
def stock_count(
    data: StockCountCreate, ctx: RestaurantContext = Depends(inv_write), db: Session = Depends(get_db)
) -> MovementOut | None:
    # Returns null when the count matches the recorded balance (no movement needed).
    return inventory_service.record_stock_count(db, ctx, data)


@router.get("/recipes", response_model=list[RecipeSummary], tags=["recipes"])
def list_recipes(
    ctx: RestaurantContext = Depends(require(Permission.RECIPES_READ)), db: Session = Depends(get_db)
) -> list[RecipeSummary]:
    return recipe_service.list_recipe_summaries(db, ctx)


@router.get(
    "/recipes/products/{product_id}",
    response_model=RecipeOut | None,
    tags=["recipes"],
    summary="The product's active recipe, or null when it has none yet",
)
def get_recipe(
    product_id: uuid.UUID,
    ctx: RestaurantContext = Depends(require(Permission.RECIPES_READ)),
    db: Session = Depends(get_db),
) -> RecipeOut | None:
    return recipe_service.get_product_recipe(db, ctx, product_id)


@router.get("/recipes/products/{product_id}/versions", response_model=list[RecipeOut], tags=["recipes"])
def recipe_versions(
    product_id: uuid.UUID,
    ctx: RestaurantContext = Depends(require(Permission.RECIPES_READ)),
    db: Session = Depends(get_db),
) -> list[RecipeOut]:
    return recipe_service.list_versions(db, ctx, product_id)


@router.put(
    "/recipes/products/{product_id}",
    response_model=RecipeOut,
    tags=["recipes"],
    summary="Save a recipe (creates a new version when it changes)",
)
def set_recipe(
    product_id: uuid.UUID,
    data: RecipeSet,
    ctx: RestaurantContext = Depends(require(Permission.RECIPES_WRITE)),
    db: Session = Depends(get_db),
) -> RecipeOut:
    return recipe_service.set_recipe(db, ctx, product_id, data)


@router.delete("/recipes/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["recipes"])
def remove_recipe(
    product_id: uuid.UUID,
    ctx: RestaurantContext = Depends(require(Permission.RECIPES_WRITE)),
    db: Session = Depends(get_db),
) -> Response:
    recipe_service.remove_recipe(db, ctx, product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
