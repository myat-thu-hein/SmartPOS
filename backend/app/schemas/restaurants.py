"""Restaurant settings, payment method and discount schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import available_timezones

from pydantic import EmailStr, Field, field_validator, model_validator

from app.models.enums import DiscountKind, PaymentMethodKind
from app.schemas.common import ORMModel, RequestModel
from app.utils.types import LongText, Name


class RestaurantOut(ORMModel):
    id: uuid.UUID
    name: str
    legal_name: str | None
    branch_name: str | None
    tax_id: str | None
    address: str | None
    phone: str | None
    email: str | None
    currency: str
    timezone: str
    locale: str
    tax_rate_bps: int
    tax_label: str
    prices_include_tax: bool
    service_charge_bps: int
    service_charge_taxable: bool
    service_charge_dine_in_only: bool
    max_cashier_discount_bps: int
    allow_negative_stock: bool
    loyalty_enabled: bool
    loyalty_spend_per_point_minor: int
    loyalty_point_value_minor: int
    receipt_header: str | None
    receipt_footer: str | None
    order_number_prefix: str
    is_active: bool
    is_demo: bool
    created_at: datetime


class RestaurantSummary(ORMModel):
    id: uuid.UUID
    name: str
    branch_name: str | None
    is_active: bool
    is_demo: bool
    created_at: datetime


def _check_timezone(value: str | None) -> str | None:
    if value is not None and value not in available_timezones():
        raise ValueError("Unknown time zone")
    return value


class RestaurantSettingsUpdate(RequestModel):
    name: Name | None = None
    legal_name: str | None = Field(default=None, max_length=200)
    branch_name: str | None = Field(default=None, max_length=100)
    tax_id: str | None = Field(default=None, max_length=32)
    address: LongText | None = None
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    timezone: str | None = None
    locale: str | None = Field(default=None, max_length=16)
    tax_rate_bps: int | None = Field(default=None, ge=0, le=5000)
    tax_label: str | None = Field(default=None, min_length=1, max_length=32)
    prices_include_tax: bool | None = None
    service_charge_bps: int | None = Field(default=None, ge=0, le=5000)
    service_charge_taxable: bool | None = None
    service_charge_dine_in_only: bool | None = None
    max_cashier_discount_bps: int | None = Field(default=None, ge=0, le=10000)
    allow_negative_stock: bool | None = None
    loyalty_enabled: bool | None = None
    loyalty_spend_per_point_minor: int | None = Field(default=None, gt=0, le=10**9)
    loyalty_point_value_minor: int | None = Field(default=None, ge=0, le=10**7)
    receipt_header: LongText | None = None
    receipt_footer: LongText | None = None
    order_number_prefix: str | None = Field(default=None, max_length=8, pattern=r"^[A-Za-z0-9\-]*$")

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, value: str | None) -> str | None:
        return _check_timezone(value)


class RestaurantCreate(RequestModel):
    name: Name
    branch_name: str | None = Field(default=None, max_length=100)
    timezone: str = "Asia/Bangkok"
    currency: str = Field(default="THB", pattern="^[A-Z]{3}$")
    manager_email: EmailStr | None = None

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, value: str | None) -> str | None:
        return _check_timezone(value)


class PaymentMethodOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    kind: PaymentMethodKind
    is_simulated: bool
    is_active: bool
    display_order: int


class PaymentMethodCreate(RequestModel):
    code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Z0-9_]+$")
    name: Name
    kind: PaymentMethodKind
    display_order: int = Field(default=0, ge=0, le=1000)


class PaymentMethodUpdate(RequestModel):
    name: Name | None = None
    is_active: bool | None = None
    display_order: int | None = Field(default=None, ge=0, le=1000)


class DiscountOut(ORMModel):
    id: uuid.UUID
    name: str
    kind: DiscountKind
    value: int
    requires_manager: bool
    is_active: bool


class DiscountCreate(RequestModel):
    name: Name
    kind: DiscountKind
    value: int = Field(gt=0, le=10**12)
    requires_manager: bool = False

    @model_validator(mode="after")
    def _percent_range(self) -> DiscountCreate:
        if self.kind == DiscountKind.PERCENT and self.value > 10000:
            raise ValueError("Percentage discounts are expressed in basis points (max 10000 = 100%).")
        return self


class DiscountUpdate(RequestModel):
    name: Name | None = None
    value: int | None = Field(default=None, gt=0, le=10**12)
    requires_manager: bool | None = None
    is_active: bool | None = None


class AuditLogOut(ORMModel):
    id: uuid.UUID
    restaurant_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None
    actor_email: str | None = None
    action: str
    entity_type: str | None
    entity_id: str | None
    details: dict | None
    ip_address: str | None
    request_id: str | None
    created_at: datetime
