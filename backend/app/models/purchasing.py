"""Suppliers, supplier price lists, purchase orders and goods receipts."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import QTY, UNIT_COST, ZERO, Base, created_at_col, str_enum, updated_at_col, uuid_pk
from app.models.enums import PurchaseOrderStatus


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(320))
    address: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False, default=2, server_default="2")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        UniqueConstraint("restaurant_id", "name"),
        CheckConstraint("lead_time_days >= 0 AND lead_time_days <= 365", name="lead_time_range"),
    )


class SupplierIngredient(Base):
    """A supplier's reference and price for an ingredient."""

    __tablename__ = "supplier_ingredients"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_sku: Mapped[str | None] = mapped_column(String(64))
    # Price per base unit of the ingredient, in minor units.
    unit_cost_minor: Mapped[Decimal | None] = mapped_column(UNIT_COST)
    # Minimum quantity per order in base units (e.g. a 1000 g bag).
    min_order_quantity: Mapped[Decimal | None] = mapped_column(QTY)
    lead_time_days: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        UniqueConstraint("supplier_id", "ingredient_id"),
        CheckConstraint("min_order_quantity IS NULL OR min_order_quantity > 0", name="moq_positive"),
        CheckConstraint("unit_cost_minor IS NULL OR unit_cost_minor >= 0", name="cost_nonnegative"),
    )


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False)
    po_number: Mapped[int] = mapped_column(Integer, nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[PurchaseOrderStatus] = mapped_column(
        str_enum(PurchaseOrderStatus, 24), nullable=False, default=PurchaseOrderStatus.DRAFT
    )
    expected_delivery_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    estimated_total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    items: Mapped[list[PurchaseOrderItem]] = relationship(
        back_populates="purchase_order", cascade="all, delete-orphan", order_by="PurchaseOrderItem.position"
    )
    receipts: Mapped[list[PurchaseOrderReceipt]] = relationship(
        back_populates="purchase_order", order_by="PurchaseOrderReceipt.created_at"
    )

    __table_args__ = (
        UniqueConstraint("restaurant_id", "po_number"),
        Index("ix_purchase_orders_status", "restaurant_id", "status"),
    )


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id: Mapped[uuid.UUID] = uuid_pk()
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=False)
    # Quantities are in the ingredient's base unit.
    quantity_ordered: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    quantity_received: Mapped[Decimal] = mapped_column(QTY, nullable=False, default=ZERO, server_default="0")
    input_quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    input_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    # Expected cost per base unit, in minor units.
    unit_cost_minor: Mapped[Decimal] = mapped_column(UNIT_COST, nullable=False, default=ZERO)

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="items")

    __table_args__ = (
        CheckConstraint("quantity_ordered > 0", name="ordered_positive"),
        CheckConstraint("quantity_received >= 0 AND quantity_received <= quantity_ordered", name="received_range"),
        UniqueConstraint("purchase_order_id", "ingredient_id"),
    )


class PurchaseOrderReceipt(Base):
    """One delivery (full or partial) received against a purchase order."""

    __tablename__ = "purchase_order_receipts"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    total_cost_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    received_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at_col()

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="receipts")
    lines: Mapped[list[PurchaseOrderReceiptLine]] = relationship(back_populates="receipt", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("restaurant_id", "idempotency_key"),)


class PurchaseOrderReceiptLine(Base):
    __tablename__ = "purchase_order_receipt_lines"

    id: Mapped[uuid.UUID] = uuid_pk()
    receipt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("purchase_order_receipts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purchase_order_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("purchase_order_items.id", ondelete="CASCADE"), nullable=False
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    unit_cost_minor: Mapped[Decimal] = mapped_column(UNIT_COST, nullable=False)

    receipt: Mapped[PurchaseOrderReceipt] = relationship(back_populates="lines")

    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)
