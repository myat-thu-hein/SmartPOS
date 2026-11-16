"""Menu catalog and table schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

from app.models.enums import SelectionType, TableStatus
from app.schemas.common import ORMModel, RequestModel
from app.utils.types import LongText, Name, OptionalQty, PositiveQtyIn


class CategoryCreate(RequestModel):
    name: Name
    description: LongText | None = None
    display_order: int = Field(default=0, ge=0, le=10000)
    is_active: bool = True


class CategoryUpdate(RequestModel):
    name: Name | None = None
    description: LongText | None = None
    display_order: int | None = Field(default=None, ge=0, le=10000)
    is_active: bool | None = None


class CategoryOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None
    display_order: int
    is_active: bool
    product_count: int = 0
    created_at: datetime
    updated_at: datetime


class ModifierOptionCreate(RequestModel):
    name: Name
    price_delta_minor: int = Field(default=0, ge=-(10**9), le=10**9)
    is_default: bool = False
    display_order: int = Field(default=0, ge=0, le=10000)
    ingredient_id: uuid.UUID | None = None
    ingredient_quantity: PositiveQtyIn | None = None
    ingredient_unit: str | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def _ingredient_pair(self) -> ModifierOptionCreate:
        if (self.ingredient_id is None) != (self.ingredient_quantity is None):
            raise ValueError("ingredient_id and ingredient_quantity must be provided together")
        return self


class ModifierOptionUpdate(RequestModel):
    name: Name | None = None
    price_delta_minor: int | None = Field(default=None, ge=-(10**9), le=10**9)
    is_default: bool | None = None
    is_active: bool | None = None
    display_order: int | None = Field(default=None, ge=0, le=10000)
    ingredient_id: uuid.UUID | None = None
    ingredient_quantity: PositiveQtyIn | None = None
    ingredient_unit: str | None = Field(default=None, max_length=20)
    clear_ingredient: bool = False


class ModifierOptionOut(ORMModel):
    id: uuid.UUID
    group_id: uuid.UUID
    name: str
    price_delta_minor: int
    is_default: bool
    is_active: bool
    display_order: int
    ingredient_id: uuid.UUID | None
    ingredient_quantity: OptionalQty


class ModifierGroupCreate(RequestModel):
    name: Name
    description: LongText | None = None
    selection_type: SelectionType
    min_select: int = Field(default=0, ge=0, le=20)
    max_select: int | None = Field(default=None, ge=1, le=20)
    display_order: int = Field(default=0, ge=0, le=10000)
    options: list[ModifierOptionCreate] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def _selection_rules(self) -> ModifierGroupCreate:
        validate_selection_rules(self.selection_type, self.min_select, self.max_select)
        return self


def validate_selection_rules(selection_type: SelectionType, min_select: int, max_select: int | None) -> None:
    if selection_type == SelectionType.SINGLE and (max_select not in (None, 1) or min_select > 1):
        raise ValueError("Single-choice groups allow at most one option (min_select 0 or 1)")
    if max_select is not None and max_select < min_select:
        raise ValueError("max_select must be greater than or equal to min_select")


class ModifierGroupUpdate(RequestModel):
    name: Name | None = None
    description: LongText | None = None
    selection_type: SelectionType | None = None
    min_select: int | None = Field(default=None, ge=0, le=20)
    max_select: int | None = Field(default=None, ge=1, le=20)
    clear_max_select: bool = False
    display_order: int | None = Field(default=None, ge=0, le=10000)
    is_active: bool | None = None


class ModifierGroupOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None
    selection_type: SelectionType
    min_select: int
    max_select: int | None
    display_order: int
    is_active: bool
    options: list[ModifierOptionOut]


class ProductCreate(RequestModel):
    category_id: uuid.UUID
    name: Name
    description: LongText | None = None
    sku: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9\-_.]+$")
    image_url: HttpUrl | None = None
    price_minor: int = Field(ge=0, le=10**10)
    is_available: bool = True
    modifier_group_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)


class ProductUpdate(RequestModel):
    category_id: uuid.UUID | None = None
    name: Name | None = None
    description: LongText | None = None
    sku: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9\-_.]+$")
    image_url: HttpUrl | None = None
    price_minor: int | None = Field(default=None, ge=0, le=10**10)
    is_available: bool | None = None
    is_active: bool | None = None


class ProductModifierGroupsUpdate(RequestModel):
    modifier_group_ids: list[uuid.UUID] = Field(max_length=20)


class ProductOut(ORMModel):
    id: uuid.UUID
    category_id: uuid.UUID
    category_name: str | None = None
    name: str
    description: str | None
    sku: str | None
    image_url: str | None
    price_minor: int
    is_available: bool
    is_active: bool
    has_recipe: bool = False
    modifier_groups: list[ModifierGroupOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class TableCreate(RequestModel):
    name: str = Field(min_length=1, max_length=50)
    capacity: int = Field(default=4, ge=1, le=100)
    zone: str | None = Field(default=None, max_length=50)
    layout_x: int | None = Field(default=None, ge=0, le=100)
    layout_y: int | None = Field(default=None, ge=0, le=100)


class TableUpdate(RequestModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    capacity: int | None = Field(default=None, ge=1, le=100)
    zone: str | None = Field(default=None, max_length=50)
    layout_x: int | None = Field(default=None, ge=0, le=100)
    layout_y: int | None = Field(default=None, ge=0, le=100)
    is_active: bool | None = None


class TableStatusUpdate(RequestModel):
    status: TableStatus


class TableOrderSummary(BaseModel):
    id: uuid.UUID
    order_number: int
    display_number: str
    status: str
    payment_status: str
    total_minor: int
    item_count: int
    created_at: datetime


class TableOut(ORMModel):
    id: uuid.UUID
    name: str
    capacity: int
    zone: str | None
    status: TableStatus
    current_order_id: uuid.UUID | None
    layout_x: int | None
    layout_y: int | None
    is_active: bool
    current_order: TableOrderSummary | None = None


class ProductSuggestion(BaseModel):
    """A POS add-on suggestion and the sales evidence behind it."""

    product_id: uuid.UUID
    product_name: str
    kind: Literal["ordered_together", "customer_usual", "popular_now"]
    reason: str
    score: float
    evidence: dict[str, int | float]
