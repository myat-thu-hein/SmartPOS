"""Orders, order items, payments, refunds and pricing configuration."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import QTY, Base, created_at_col, str_enum, updated_at_col, uuid_pk
from app.models.enums import (
    DiscountKind,
    OrderStatus,
    OrderType,
    PaymentMethodKind,
    PaymentRecordStatus,
    PaymentStatus,
)


class PaymentMethod(Base):
    __tablename__ = "payment_methods"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[PaymentMethodKind] = mapped_column(str_enum(PaymentMethodKind, 16), nullable=False)
    # True when SmartPOS only records that a payment happened elsewhere (cash
    # drawer, external card terminal, QR shown to the customer) without any
    # provider confirming the transfer.
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (UniqueConstraint("restaurant_id", "code"),)


class Discount(Base):
    __tablename__ = "discounts"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[DiscountKind] = mapped_column(str_enum(DiscountKind, 16), nullable=False)
    # Basis points for PERCENT (1000 = 10 %), minor units for FIXED.
    value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    requires_manager: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        UniqueConstraint("restaurant_id", "name"),
        CheckConstraint("value > 0", name="value_positive"),
        CheckConstraint("kind <> 'PERCENT' OR value <= 10000", name="percent_max"),
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False)
    order_number: Mapped[int] = mapped_column(Integer, nullable=False)
    order_type: Mapped[OrderType] = mapped_column(str_enum(OrderType, 16), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(str_enum(OrderStatus, 16), nullable=False, default=OrderStatus.DRAFT)
    payment_status: Mapped[PaymentStatus] = mapped_column(
        str_enum(PaymentStatus, 24), nullable=False, default=PaymentStatus.UNPAID
    )
    table_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("dining_tables.id", ondelete="SET NULL"))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    # Discount snapshot.
    discount_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("discounts.id", ondelete="SET NULL"))
    discount_name: Mapped[str | None] = mapped_column(String(100))
    discount_kind: Mapped[DiscountKind | None] = mapped_column(str_enum(DiscountKind, 16))
    discount_value: Mapped[int | None] = mapped_column(BigInteger)
    discount_reason: Mapped[str | None] = mapped_column(String(200))
    discount_applied_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    loyalty_points_redeemed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # Authoritative totals computed by the backend pricing engine (minor units).
    subtotal_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    discount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    loyalty_discount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    service_charge_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    tax_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    amount_paid_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    amount_refunded_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    # Pricing settings snapshot used for the totals above.
    tax_rate_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    service_charge_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prices_include_tax: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    stock_committed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    idempotency_key: Mapped[str | None] = mapped_column(String(100))

    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    preparing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderItem.position"
    )
    payments: Mapped[list[Payment]] = relationship(back_populates="order", order_by="Payment.created_at")
    refunds: Mapped[list[Refund]] = relationship(back_populates="order", order_by="Refund.created_at")

    __table_args__ = (
        UniqueConstraint("restaurant_id", "order_number"),
        UniqueConstraint("restaurant_id", "idempotency_key"),
        CheckConstraint("total_minor >= 0", name="total_nonnegative"),
        CheckConstraint("amount_paid_minor >= 0", name="paid_nonnegative"),
        CheckConstraint(
            "amount_refunded_minor >= 0 AND amount_refunded_minor <= amount_paid_minor", name="refund_le_paid"
        ),
        Index("ix_orders_status", "restaurant_id", "status"),
        Index("ix_orders_paid_at", "restaurant_id", "paid_at"),
        Index("ix_orders_created_at", "restaurant_id", "created_at"),
        Index("ix_orders_table", "table_id"),
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Snapshots so receipts and analytics stay correct after menu changes.
    product_name: Mapped[str] = mapped_column(String(150), nullable=False)
    product_sku: Mapped[str | None] = mapped_column(String(64))
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    category_name: Mapped[str | None] = mapped_column(String(100))
    base_price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unit_price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(300))
    # Recipe version used for the stock deduction of this line (set on confirmation).
    recipe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recipes.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at_col()

    order: Mapped[Order] = relationship(back_populates="items")
    modifiers: Mapped[list[OrderItemModifier]] = relationship(back_populates="order_item", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("quantity > 0 AND quantity <= 999", name="quantity_range"),
        CheckConstraint("unit_price_minor >= 0", name="unit_price_nonnegative"),
    )


class OrderItemModifier(Base):
    __tablename__ = "order_item_modifiers"

    id: Mapped[uuid.UUID] = uuid_pk()
    order_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("order_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    modifier_option_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("modifier_options.id", ondelete="SET NULL"))
    group_name: Mapped[str] = mapped_column(String(100), nullable=False)
    option_name: Mapped[str] = mapped_column(String(100), nullable=False)
    price_delta_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    ingredient_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingredients.id", ondelete="SET NULL"))
    ingredient_quantity: Mapped[Decimal | None] = mapped_column(QTY)

    order_item: Mapped[OrderItem] = relationship(back_populates="modifiers")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    payment_method_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payment_methods.id", ondelete="SET NULL"))
    method_code: Mapped[str] = mapped_column(String(32), nullable=False)
    method_name: Mapped[str] = mapped_column(String(100), nullable=False)
    method_kind: Mapped[PaymentMethodKind] = mapped_column(str_enum(PaymentMethodKind, 16), nullable=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[PaymentRecordStatus] = mapped_column(
        str_enum(PaymentRecordStatus, 24), nullable=False, default=PaymentRecordStatus.RECORDED
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_tendered_minor: Mapped[int | None] = mapped_column(BigInteger)
    change_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    refunded_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    reference: Mapped[str | None] = mapped_column(String(100))
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at_col()

    order: Mapped[Order] = relationship(back_populates="payments")

    __table_args__ = (
        UniqueConstraint("restaurant_id", "idempotency_key"),
        CheckConstraint("amount_minor > 0", name="amount_positive"),
        CheckConstraint("refunded_minor >= 0 AND refunded_minor <= amount_minor", name="refund_le_amount"),
        Index("ix_payments_time", "restaurant_id", "created_at"),
    )


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id", ondelete="RESTRICT"), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at_col()

    order: Mapped[Order] = relationship(back_populates="refunds")

    __table_args__ = (
        UniqueConstraint("restaurant_id", "idempotency_key"),
        CheckConstraint("amount_minor > 0", name="amount_positive"),
        Index("ix_refunds_time", "restaurant_id", "created_at"),
    )
