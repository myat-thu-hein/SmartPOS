"""Ingredient, recipe and inventory movement schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import BaseUnit, MovementType
from app.schemas.common import ORMModel, RequestModel
from app.utils.types import Name, NonNegativeQtyIn, OptionalQty, PositiveQtyIn, Qty, ShortText


class IngredientUnitIn(RequestModel):
    unit_name: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z][A-Za-z0-9 _\-]*$")
    factor_to_base: Decimal = Field(gt=0, max_digits=14, decimal_places=4)


class IngredientUnitOut(ORMModel):
    id: uuid.UUID
    unit_name: str
    factor_to_base: Qty


class IngredientCreate(RequestModel):
    name: Name
    sku: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9\-_.]+$")
    base_unit: BaseUnit
    reorder_level: NonNegativeQtyIn = Decimal(0)
    safety_stock: NonNegativeQtyIn = Decimal(0)
    default_supplier_id: uuid.UUID | None = None
    units: list[IngredientUnitIn] = Field(default_factory=list, max_length=10)
    opening_stock: NonNegativeQtyIn | None = None
    opening_unit_cost_minor: Decimal | None = Field(default=None, ge=0, max_digits=16, decimal_places=4)


class IngredientUpdate(RequestModel):
    name: Name | None = None
    sku: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9\-_.]+$")
    reorder_level: NonNegativeQtyIn | None = None
    safety_stock: NonNegativeQtyIn | None = None
    default_supplier_id: uuid.UUID | None = None
    clear_default_supplier: bool = False
    is_active: bool | None = None


class IngredientOut(ORMModel):
    id: uuid.UUID
    name: str
    sku: str | None
    base_unit: BaseUnit
    current_stock: Qty
    reorder_level: Qty
    safety_stock: Qty
    average_cost_minor: Qty
    stock_value_minor: int = 0
    default_supplier_id: uuid.UUID | None
    default_supplier_name: str | None = None
    is_active: bool
    is_low_stock: bool = False
    units: list[IngredientUnitOut] = Field(default_factory=list)
    allowed_units: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class RecipeItemIn(RequestModel):
    ingredient_id: uuid.UUID
    quantity: PositiveQtyIn
    unit: str | None = Field(default=None, max_length=20, description="Defaults to the ingredient base unit")
    waste_factor: Decimal = Field(default=Decimal(0), ge=0, lt=1, max_digits=5, decimal_places=4)


class RecipeSet(RequestModel):
    items: list[RecipeItemIn] = Field(min_length=1, max_length=50)
    notes: ShortText | None = None

    @model_validator(mode="after")
    def _unique_ingredients(self) -> RecipeSet:
        ids = [i.ingredient_id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Each ingredient may appear only once in a recipe")
        return self


class RecipeItemOut(BaseModel):
    id: uuid.UUID
    ingredient_id: uuid.UUID
    ingredient_name: str
    base_unit: BaseUnit
    quantity: Qty
    input_quantity: Qty
    input_unit: str
    waste_factor: Qty
    effective_quantity: Qty
    estimated_cost_minor: Qty


class RecipeOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    version: int
    is_active: bool
    notes: str | None
    created_at: datetime
    items: list[RecipeItemOut]
    estimated_cost_minor: Qty
    selling_price_minor: int
    estimated_margin_bps: int | None


class RecipeSummary(BaseModel):
    product_id: uuid.UUID
    product_name: str
    category_name: str | None
    price_minor: int
    is_available: bool
    recipe_id: uuid.UUID | None
    version: int | None
    ingredient_count: int
    estimated_cost_minor: Qty | None


class MovementCreate(RequestModel):
    ingredient_id: uuid.UUID
    movement_type: MovementType = Field(description="RECEIPT, ISSUE, ADJUSTMENT or WASTE")
    quantity: Decimal = Field(
        max_digits=14, decimal_places=3, description="Positive amount; ADJUSTMENT accepts a signed value"
    )
    unit: str | None = Field(default=None, max_length=20)
    unit_cost_minor: Decimal | None = Field(
        default=None, ge=0, max_digits=16, decimal_places=4, description="Cost per entered unit (receipts only)"
    )
    reason: str = Field(min_length=3, max_length=300)


class StockCountCreate(RequestModel):
    ingredient_id: uuid.UUID
    counted_quantity: NonNegativeQtyIn
    unit: str | None = Field(default=None, max_length=20)
    reason: str = Field(default="Stock count", min_length=3, max_length=300)


class MovementOut(ORMModel):
    id: uuid.UUID
    ingredient_id: uuid.UUID
    ingredient_name: str | None = None
    base_unit: str | None = None
    movement_type: MovementType
    quantity: Qty
    balance_after: Qty
    unit_cost_minor: OptionalQty
    input_quantity: OptionalQty
    input_unit: str | None
    reason: str | None
    order_id: uuid.UUID | None
    purchase_order_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None
    actor_name: str | None = None
    created_at: datetime


class InventorySummary(BaseModel):
    ingredient_count: int
    low_stock_count: int
    out_of_stock_count: int
    total_value_minor: int
    valued_ingredient_count: int
    unvalued_ingredient_count: int
