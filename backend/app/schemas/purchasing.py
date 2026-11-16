"""Supplier and purchase order schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.models.enums import PurchaseOrderStatus
from app.schemas.common import ORMModel, RequestModel
from app.utils.types import LongText, Name, OptionalQty, PositiveQtyIn, Qty


class SupplierCreate(RequestModel):
    name: Name
    contact_name: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    address: LongText | None = None
    notes: LongText | None = None
    lead_time_days: int = Field(default=2, ge=0, le=365)


class SupplierUpdate(RequestModel):
    name: Name | None = None
    contact_name: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    address: LongText | None = None
    notes: LongText | None = None
    lead_time_days: int | None = Field(default=None, ge=0, le=365)
    is_active: bool | None = None


class SupplierOut(ORMModel):
    id: uuid.UUID
    name: str
    contact_name: str | None
    phone: str | None
    email: str | None
    address: str | None
    notes: str | None
    lead_time_days: int
    is_active: bool
    ingredient_count: int = 0
    open_purchase_orders: int = 0
    created_at: datetime


class SupplierIngredientIn(RequestModel):
    ingredient_id: uuid.UUID
    supplier_sku: str | None = Field(default=None, max_length=64)
    unit_cost_minor: Decimal | None = Field(
        default=None, ge=0, max_digits=16, decimal_places=4, description="Price per `unit` in minor currency units"
    )
    unit: str | None = Field(default=None, max_length=20, description="Unit for price and minimum order quantity")
    min_order_quantity: PositiveQtyIn | None = None
    lead_time_days: int | None = Field(default=None, ge=0, le=365)


class SupplierIngredientUpdate(RequestModel):
    supplier_sku: str | None = Field(default=None, max_length=64)
    unit_cost_minor: Decimal | None = Field(default=None, ge=0, max_digits=16, decimal_places=4)
    unit: str | None = Field(default=None, max_length=20)
    min_order_quantity: PositiveQtyIn | None = None
    lead_time_days: int | None = Field(default=None, ge=0, le=365)


class SupplierIngredientOut(ORMModel):
    id: uuid.UUID
    supplier_id: uuid.UUID
    ingredient_id: uuid.UUID
    ingredient_name: str | None = None
    base_unit: str | None = None
    supplier_sku: str | None
    unit_cost_minor: OptionalQty
    min_order_quantity: OptionalQty
    lead_time_days: int | None


class PurchaseOrderItemIn(RequestModel):
    ingredient_id: uuid.UUID
    quantity: PositiveQtyIn
    unit: str | None = Field(default=None, max_length=20)
    unit_cost_minor: Decimal | None = Field(
        default=None, ge=0, max_digits=16, decimal_places=4, description="Expected price per entered unit"
    )


class PurchaseOrderCreate(RequestModel):
    supplier_id: uuid.UUID
    expected_delivery_date: date | None = None
    notes: LongText | None = None
    items: list[PurchaseOrderItemIn] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _unique(self) -> PurchaseOrderCreate:
        ids = [i.ingredient_id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Each ingredient may appear only once per purchase order")
        return self


class PurchaseOrderUpdate(RequestModel):
    expected_delivery_date: date | None = None
    notes: LongText | None = None
    items: list[PurchaseOrderItemIn] | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def _unique(self) -> PurchaseOrderUpdate:
        if self.items:
            ids = [i.ingredient_id for i in self.items]
            if len(ids) != len(set(ids)):
                raise ValueError("Each ingredient may appear only once per purchase order")
        return self


class ReceiveLine(RequestModel):
    item_id: uuid.UUID
    quantity: PositiveQtyIn
    unit: str | None = Field(default=None, max_length=20)
    unit_cost_minor: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=16,
        decimal_places=4,
        description="Actual price per entered unit (defaults to the PO price)",
    )


class ReceiveRequest(RequestModel):
    lines: list[ReceiveLine] = Field(min_length=1, max_length=100)
    notes: LongText | None = None


class CancelPurchaseOrder(RequestModel):
    reason: str = Field(min_length=3, max_length=300)


class PurchaseOrderItemOut(ORMModel):
    id: uuid.UUID
    ingredient_id: uuid.UUID
    ingredient_name: str | None = None
    base_unit: str | None = None
    quantity_ordered: Qty
    quantity_received: Qty
    quantity_remaining: Qty = Decimal(0)
    input_quantity: Qty
    input_unit: str
    unit_cost_minor: Qty
    line_total_minor: int = 0


class ReceiptLineOut(ORMModel):
    id: uuid.UUID
    purchase_order_item_id: uuid.UUID
    ingredient_id: uuid.UUID
    quantity: Qty
    unit_cost_minor: Qty


class ReceiptOut(ORMModel):
    id: uuid.UUID
    notes: str | None
    total_cost_minor: int
    received_by: uuid.UUID | None
    created_at: datetime
    lines: list[ReceiptLineOut]


class PurchaseOrderOut(ORMModel):
    id: uuid.UUID
    po_number: int
    display_number: str = ""
    supplier_id: uuid.UUID
    supplier_name: str | None = None
    status: PurchaseOrderStatus
    expected_delivery_date: date | None
    notes: str | None
    estimated_total_minor: int
    received_total_minor: int = 0
    created_by: uuid.UUID | None
    submitted_at: datetime | None
    received_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    created_at: datetime
    updated_at: datetime
    items: list[PurchaseOrderItemOut]
    receipts: list[ReceiptOut] = Field(default_factory=list)


class PurchaseOrderListItem(BaseModel):
    id: uuid.UUID
    po_number: int
    display_number: str
    supplier_id: uuid.UUID
    supplier_name: str
    status: PurchaseOrderStatus
    expected_delivery_date: date | None
    estimated_total_minor: int
    item_count: int
    created_at: datetime
