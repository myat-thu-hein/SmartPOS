"""Customer and loyalty schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import LoyaltyTransactionType
from app.schemas.common import ORMModel, RequestModel
from app.utils.types import LongText, Name

PHONE_PATTERN = r"^\+?[0-9 ()\-]{6,24}$"


class CustomerCreate(RequestModel):
    name: Name
    phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    email: EmailStr | None = None
    notes: LongText | None = None


class CustomerUpdate(RequestModel):
    name: Name | None = None
    phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    email: EmailStr | None = None
    notes: LongText | None = None


class CustomerLookup(BaseModel):
    """What front-of-house staff need at the till; contact details are masked."""

    id: uuid.UUID
    name: str
    phone_masked: str | None
    loyalty_balance: int


class CustomerOut(ORMModel):
    id: uuid.UUID
    name: str
    phone: str | None
    email: str | None
    notes: str | None
    loyalty_balance: int
    created_at: datetime
    updated_at: datetime
    order_count: int = 0
    total_spent_minor: int = 0
    last_order_at: datetime | None = None


class CustomerFavourite(BaseModel):
    """A product this customer buys repeatedly, from their settled orders."""

    product_id: uuid.UUID
    product_name: str
    orders: int
    quantity: int
    last_ordered_at: datetime


class LoyaltyTransactionOut(ORMModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    order_id: uuid.UUID | None
    transaction_type: LoyaltyTransactionType
    points: int
    balance_after: int
    reason: str | None
    created_by: uuid.UUID | None
    created_at: datetime


class LoyaltyAdjust(RequestModel):
    points: int = Field(ge=-1_000_000, le=1_000_000)
    reason: str = Field(min_length=3, max_length=300)


class LoyaltySettingsOut(BaseModel):
    loyalty_enabled: bool
    loyalty_spend_per_point_minor: int
    loyalty_point_value_minor: int
    description: str
