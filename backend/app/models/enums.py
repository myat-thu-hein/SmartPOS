"""Enumerations shared by models, schemas and services."""

from __future__ import annotations

import enum


class RestaurantRole(enum.StrEnum):
    MANAGER = "MANAGER"
    CASHIER = "CASHIER"
    KITCHEN = "KITCHEN"


class TableStatus(enum.StrEnum):
    AVAILABLE = "AVAILABLE"
    OCCUPIED = "OCCUPIED"
    RESERVED = "RESERVED"
    CLEANING = "CLEANING"


class SelectionType(enum.StrEnum):
    SINGLE = "SINGLE"
    MULTIPLE = "MULTIPLE"


class OrderType(enum.StrEnum):
    DINE_IN = "DINE_IN"
    TAKEAWAY = "TAKEAWAY"


class OrderStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    PREPARING = "PREPARING"
    READY = "READY"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class PaymentStatus(enum.StrEnum):
    UNPAID = "UNPAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    REFUNDED = "REFUNDED"


class PaymentMethodKind(enum.StrEnum):
    CASH = "CASH"
    CARD = "CARD"
    QR = "QR"
    OTHER = "OTHER"


class PaymentRecordStatus(enum.StrEnum):
    # Recorded locally by staff. No payment provider has confirmed it.
    RECORDED = "RECORDED"
    # Reserved for future provider integrations that confirm a payment.
    PROVIDER_CONFIRMED = "PROVIDER_CONFIRMED"


class DiscountKind(enum.StrEnum):
    PERCENT = "PERCENT"
    FIXED = "FIXED"


class BaseUnit(enum.StrEnum):
    GRAM = "g"
    MILLILITRE = "ml"
    PIECE = "piece"


class MovementType(enum.StrEnum):
    OPENING = "OPENING"
    RECEIPT = "RECEIPT"
    PURCHASE_RECEIPT = "PURCHASE_RECEIPT"
    ISSUE = "ISSUE"
    ADJUSTMENT = "ADJUSTMENT"
    WASTE = "WASTE"
    SALE = "SALE"
    SALE_REVERSAL = "SALE_REVERSAL"


class PurchaseOrderStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    RECEIVED = "RECEIVED"
    CANCELLED = "CANCELLED"


class LoyaltyTransactionType(enum.StrEnum):
    EARN = "EARN"
    REDEEM = "REDEEM"
    ADJUST = "ADJUST"
    REVERSAL = "REVERSAL"


class ForecastTarget(enum.StrEnum):
    PRODUCT = "PRODUCT"
    INGREDIENT = "INGREDIENT"


class RecommendationStatus(enum.StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    MODIFIED = "MODIFIED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
