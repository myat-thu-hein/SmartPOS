"""Menu catalog: categories, products, modifiers and dining tables."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import QTY, Base, created_at_col, str_enum, updated_at_col, uuid_pk
from app.models.enums import SelectionType, TableStatus

product_modifier_groups = Table(
    "product_modifier_groups",
    Base.metadata,
    Column("product_id", UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "modifier_group_id", UUID(as_uuid=True), ForeignKey("modifier_groups.id", ondelete="CASCADE"), primary_key=True
    ),
    Column("display_order", Integer, nullable=False, server_default="0"),
)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (UniqueConstraint("restaurant_id", "name"),)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sku: Mapped[str | None] = mapped_column(String(64))
    image_url: Mapped[str | None] = mapped_column(String(500))
    price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # "Available" is the day-to-day toggle (e.g. sold out); "active" archives a
    # product without deleting historical sales that reference it.
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    category: Mapped[Category] = relationship()
    modifier_groups: Mapped[list[ModifierGroup]] = relationship(
        secondary=product_modifier_groups, order_by=product_modifier_groups.c.display_order
    )

    __table_args__ = (
        UniqueConstraint("restaurant_id", "sku"),
        CheckConstraint("price_minor >= 0", name="price_nonnegative"),
    )


class ModifierGroup(Base):
    __tablename__ = "modifier_groups"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    selection_type: Mapped[SelectionType] = mapped_column(str_enum(SelectionType, 16), nullable=False)
    min_select: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_select: Mapped[int | None] = mapped_column(Integer)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    options: Mapped[list[ModifierOption]] = relationship(
        back_populates="group", order_by="ModifierOption.display_order", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("restaurant_id", "name"),
        CheckConstraint("min_select >= 0", name="min_nonnegative"),
        CheckConstraint("max_select IS NULL OR (max_select >= 1 AND max_select >= min_select)", name="max_valid"),
    )


class ModifierOption(Base):
    __tablename__ = "modifier_options"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("modifier_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    price_delta_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Optional extra ingredient consumed when this option is chosen (e.g. "extra egg").
    ingredient_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingredients.id", ondelete="SET NULL"))
    ingredient_quantity: Mapped[Decimal | None] = mapped_column(QTY)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    group: Mapped[ModifierGroup] = relationship(back_populates="options")

    __table_args__ = (
        UniqueConstraint("group_id", "name"),
        CheckConstraint("ingredient_quantity IS NULL OR ingredient_quantity > 0", name="ingredient_qty_positive"),
    )


class DiningTable(Base):
    __tablename__ = "dining_tables"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=4, server_default="4")
    zone: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[TableStatus] = mapped_column(
        str_enum(TableStatus, 16), nullable=False, default=TableStatus.AVAILABLE, server_default="AVAILABLE"
    )
    current_order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL", use_alter=True, name="fk_dining_tables_current_order")
    )
    layout_x: Mapped[int | None] = mapped_column(Integer)
    layout_y: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        UniqueConstraint("restaurant_id", "name"),
        CheckConstraint("capacity >= 1 AND capacity <= 100", name="capacity_range"),
        Index("ix_dining_tables_status", "restaurant_id", "status"),
    )
