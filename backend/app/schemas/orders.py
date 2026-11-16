"""Order, payment, refund, receipt and kitchen schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import (
    DiscountKind,
    OrderStatus,
    OrderType,
    PaymentMethodKind,
    PaymentRecordStatus,
    PaymentStatus,
)
from app.schemas.common import ORMModel, RequestModel
from app.utils.types import ShortText


class OrderItemIn(RequestModel):
    product_id: uuid.UUID
    quantity: int = Field(ge=1, le=999)
    modifier_option_ids: list[uuid.UUID] = Field(default_factory=list, max_length=30)
    notes: str | None = Field(default=None, max_length=300)


class DiscountIn(RequestModel):
    """Either a configured discount (`discount_id`) or a manager-only custom discount."""

    discount_id: uuid.UUID | None = None
    kind: DiscountKind | None = None
    value: int | None = Field(default=None, gt=0, le=10**10)
    reason: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _one_kind(self) -> DiscountIn:
        custom = self.kind is not None or self.value is not None
        if self.discount_id is None and not custom:
            raise ValueError("Provide discount_id or kind and value")
        if self.discount_id is not None and custom:
            raise ValueError("Provide either discount_id or a custom kind/value, not both")
        if custom and (self.kind is None or self.value is None):
            raise ValueError("Custom discounts need both kind and value")
        if custom and not (self.reason and self.reason.strip()):
            raise ValueError("Custom discounts need a reason")
        if self.kind == DiscountKind.PERCENT and self.value is not None and self.value > 10000:
            raise ValueError("Percentage discounts are basis points (max 10000)")
        return self


class OrderDraftIn(RequestModel):
    order_type: OrderType
    table_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=500)
    items: list[OrderItemIn] = Field(min_length=1, max_length=100)
    discount: DiscountIn | None = None
    loyalty_points_to_redeem: int = Field(default=0, ge=0, le=10**7)

    @model_validator(mode="after")
    def _table_rules(self) -> OrderDraftIn:
        if self.order_type == OrderType.DINE_IN and self.table_id is None:
            raise ValueError("Dine-in orders need a table")
        if self.order_type == OrderType.TAKEAWAY and self.table_id is not None:
            raise ValueError("Takeaway orders cannot have a table")
        if self.loyalty_points_to_redeem and self.customer_id is None:
            raise ValueError("Redeeming loyalty points requires a customer")
        return self


class OrderCreate(OrderDraftIn):
    confirm: bool = Field(default=False, description="Confirm immediately (sends to kitchen, deducts stock)")


class OrderUpdate(RequestModel):
    """Replace the order's editable content. Allowed until payment starts."""

    items: list[OrderItemIn] | None = Field(default=None, min_length=1, max_length=100)
    notes: str | None = Field(default=None, max_length=500)
    customer_id: uuid.UUID | None = None
    clear_customer: bool = False
    discount: DiscountIn | None = None
    clear_discount: bool = False
    loyalty_points_to_redeem: int | None = Field(default=None, ge=0, le=10**7)


class StatusChange(RequestModel):
    status: OrderStatus


class CancelRequest(RequestModel):
    reason: str = Field(min_length=3, max_length=300)
    restock_inventory: bool | None = Field(
        default=None,
        description="Return deducted ingredients to stock. Defaults to true only if preparation had not started.",
    )


class PaymentCreate(RequestModel):
    payment_method_id: uuid.UUID
    amount_minor: int = Field(gt=0, le=10**11)
    amount_tendered_minor: int | None = Field(default=None, gt=0, le=10**11)
    reference: str | None = Field(default=None, max_length=100)


class RefundCreate(RequestModel):
    payment_id: uuid.UUID
    amount_minor: int = Field(gt=0, le=10**11)
    reason: str = Field(min_length=3, max_length=300)


class OrderItemModifierOut(ORMModel):
    id: uuid.UUID
    modifier_option_id: uuid.UUID | None
    group_name: str
    option_name: str
    price_delta_minor: int


class OrderItemOut(ORMModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    product_sku: str | None
    category_name: str | None
    base_price_minor: int
    unit_price_minor: int
    quantity: int
    line_total_minor: int
    notes: str | None
    recipe_id: uuid.UUID | None
    modifiers: list[OrderItemModifierOut]


class PaymentOut(ORMModel):
    id: uuid.UUID
    order_id: uuid.UUID
    payment_method_id: uuid.UUID | None
    method_code: str
    method_name: str
    method_kind: PaymentMethodKind
    is_simulated: bool
    status: PaymentRecordStatus
    amount_minor: int
    amount_tendered_minor: int | None
    change_minor: int
    refunded_minor: int
    reference: str | None
    recorded_by: uuid.UUID | None
    created_at: datetime
    verification_note: str = ""


class RefundOut(ORMModel):
    id: uuid.UUID
    order_id: uuid.UUID
    payment_id: uuid.UUID
    amount_minor: int
    reason: str
    recorded_by: uuid.UUID | None
    created_at: datetime


class OrderOut(ORMModel):
    id: uuid.UUID
    order_number: int
    display_number: str = ""
    order_type: OrderType
    status: OrderStatus
    payment_status: PaymentStatus
    table_id: uuid.UUID | None
    table_name: str | None = None
    customer_id: uuid.UUID | None
    customer_name: str | None = None
    notes: str | None
    discount_id: uuid.UUID | None
    discount_name: str | None
    discount_kind: DiscountKind | None
    discount_value: int | None
    discount_reason: str | None
    loyalty_points_redeemed: int
    subtotal_minor: int
    discount_minor: int
    loyalty_discount_minor: int
    service_charge_minor: int
    tax_minor: int
    total_minor: int
    amount_paid_minor: int
    amount_refunded_minor: int
    balance_due_minor: int = 0
    tax_rate_bps: int
    service_charge_bps: int
    prices_include_tax: bool
    stock_committed: bool
    created_by: uuid.UUID | None
    created_by_name: str | None = None
    confirmed_at: datetime | None
    preparing_at: datetime | None
    ready_at: datetime | None
    completed_at: datetime | None
    paid_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemOut]
    payments: list[PaymentOut] = Field(default_factory=list)
    refunds: list[RefundOut] = Field(default_factory=list)
    allowed_transitions: list[OrderStatus] = Field(default_factory=list)


class OrderListItem(BaseModel):
    id: uuid.UUID
    order_number: int
    display_number: str
    order_type: OrderType
    status: OrderStatus
    payment_status: PaymentStatus
    table_name: str | None
    customer_name: str | None
    item_count: int
    total_minor: int
    amount_paid_minor: int
    created_at: datetime
    paid_at: datetime | None


class QuoteLine(BaseModel):
    product_id: uuid.UUID
    product_name: str
    unit_price_minor: int
    quantity: int
    line_total_minor: int
    modifiers: list[str]


class OrderQuote(BaseModel):
    lines: list[QuoteLine]
    subtotal_minor: int
    discount_minor: int
    loyalty_discount_minor: int
    service_charge_minor: int
    tax_minor: int
    total_minor: int
    prices_include_tax: bool
    tax_rate_bps: int
    service_charge_bps: int
    discount_name: str | None
    max_redeemable_points: int


class ReceiptLine(BaseModel):
    name: str
    quantity: int
    unit_price_minor: int
    line_total_minor: int
    modifiers: list[str]
    notes: str | None


class ReceiptPayment(BaseModel):
    method_name: str
    amount_minor: int
    amount_tendered_minor: int | None
    change_minor: int
    is_simulated: bool
    status: str
    reference: str | None
    created_at: datetime


class Receipt(BaseModel):
    restaurant_name: str
    legal_name: str | None
    branch_name: str | None
    tax_id: str | None
    address: str | None
    phone: str | None
    header: str | None
    footer: str | None
    currency: str
    timezone: str
    order_id: uuid.UUID
    display_number: str
    order_type: OrderType
    table_name: str | None
    customer_name: str | None
    cashier_name: str | None
    created_at: datetime
    paid_at: datetime | None
    lines: list[ReceiptLine]
    subtotal_minor: int
    discount_minor: int
    discount_label: str | None
    loyalty_discount_minor: int
    loyalty_points_redeemed: int
    service_charge_minor: int
    service_charge_bps: int
    tax_minor: int
    tax_rate_bps: int
    tax_label: str
    prices_include_tax: bool
    total_minor: int
    amount_paid_minor: int
    amount_refunded_minor: int
    balance_due_minor: int
    payment_status: PaymentStatus
    status: OrderStatus
    payments: list[ReceiptPayment]
    loyalty_points_earned: int | None
    simulated_payment_notice: str | None


class KitchenItem(BaseModel):
    id: uuid.UUID
    product_name: str
    quantity: int
    modifiers: list[str]
    notes: str | None


class KitchenTicket(BaseModel):
    order_id: uuid.UUID
    display_number: str
    order_type: OrderType
    label: str
    kitchen_status: str
    order_status: OrderStatus
    notes: str | None
    created_at: datetime
    confirmed_at: datetime | None
    preparing_at: datetime | None
    ready_at: datetime | None
    completed_at: datetime | None
    items: list[KitchenItem]


class KitchenStatusChange(RequestModel):
    status: str = Field(pattern="^(PREPARING|READY|COMPLETED)$")


class CancelResult(BaseModel):
    order: OrderOut
    stock_restored: bool
    note: ShortText | None = None
