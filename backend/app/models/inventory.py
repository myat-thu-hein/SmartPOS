"""Ingredients, unit conversions, versioned recipes and immutable stock movements."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import QTY, UNIT_COST, ZERO, Base, created_at_col, str_enum, updated_at_col, uuid_pk
from app.models.enums import BaseUnit, MovementType


class Ingredient(Base):
    __tablename__ = "ingredients"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(64))
    base_unit: Mapped[BaseUnit] = mapped_column(str_enum(BaseUnit, 8), nullable=False)
    # Cached balance. It is only ever changed together with an inventory movement
    # in the same transaction; the movement ledger is the source of truth.
    current_stock: Mapped[Decimal] = mapped_column(QTY, nullable=False, default=ZERO, server_default="0")
    reorder_level: Mapped[Decimal] = mapped_column(QTY, nullable=False, default=ZERO, server_default="0")
    safety_stock: Mapped[Decimal] = mapped_column(QTY, nullable=False, default=ZERO, server_default="0")
    # Moving average cost in minor currency units per base unit.
    average_cost_minor: Mapped[Decimal] = mapped_column(UNIT_COST, nullable=False, default=ZERO, server_default="0")
    default_supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL", use_alter=True, name="fk_ingredients_default_supplier")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    units: Mapped[list[IngredientUnit]] = relationship(back_populates="ingredient", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("restaurant_id", "name"),
        UniqueConstraint("restaurant_id", "sku"),
        CheckConstraint("reorder_level >= 0", name="reorder_nonnegative"),
        CheckConstraint("safety_stock >= 0", name="safety_nonnegative"),
        CheckConstraint("average_cost_minor >= 0", name="cost_nonnegative"),
    )


class IngredientUnit(Base):
    """Ingredient-specific pack units, e.g. 1 tray of eggs = 30 pieces."""

    __tablename__ = "ingredient_units"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_name: Mapped[str] = mapped_column(String(20), nullable=False)
    factor_to_base: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)

    ingredient: Mapped[Ingredient] = relationship(back_populates="units")

    __table_args__ = (
        UniqueConstraint("ingredient_id", "unit_name"),
        CheckConstraint("factor_to_base > 0", name="factor_positive"),
    )


class Recipe(Base):
    """A versioned recipe. Editing a recipe creates a new version; old versions
    stay immutable so historical stock deductions remain explainable."""

    __tablename__ = "recipes"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at_col()

    items: Mapped[list[RecipeItem]] = relationship(back_populates="recipe", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("product_id", "version"),
        Index("uq_recipes_one_active_per_product", "product_id", unique=True, postgresql_where=text("is_active")),
    )


class RecipeItem(Base):
    __tablename__ = "recipe_items"

    id: Mapped[uuid.UUID] = uuid_pk()
    recipe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Quantity per serving in the ingredient's base unit.
    quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    # What the user originally typed (for display), e.g. 0.1 kg.
    input_quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    input_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    # Extra fraction lost during preparation, e.g. 0.05 = 5 %.
    waste_factor: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=ZERO, server_default="0")

    recipe: Mapped[Recipe] = relationship(back_populates="items")
    ingredient: Mapped[Ingredient] = relationship()

    __table_args__ = (
        UniqueConstraint("recipe_id", "ingredient_id"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("waste_factor >= 0 AND waste_factor < 1", name="waste_range"),
    )


class InventoryMovement(Base):
    """Immutable stock ledger entry. Quantity is signed and in base units.

    A database trigger (see migrations) rejects UPDATE and DELETE statements.
    """

    __tablename__ = "inventory_movements"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=False)
    movement_type: Mapped[MovementType] = mapped_column(str_enum(MovementType, 24), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    unit_cost_minor: Mapped[Decimal | None] = mapped_column(UNIT_COST)
    input_quantity: Mapped[Decimal | None] = mapped_column(QTY)
    input_unit: Mapped[str | None] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(Text)
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"))
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("purchase_orders.id", ondelete="RESTRICT"))
    purchase_order_receipt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("purchase_order_receipts.id", ondelete="RESTRICT")
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at_col()

    ingredient: Mapped[Ingredient] = relationship()

    __table_args__ = (
        CheckConstraint("quantity <> 0", name="quantity_nonzero"),
        Index("ix_inventory_movements_ingredient_time", "restaurant_id", "ingredient_id", "created_at"),
        Index("ix_inventory_movements_type_time", "restaurant_id", "movement_type", "created_at"),
        Index("ix_inventory_movements_order", "order_id"),
        Index("ix_inventory_movements_po", "purchase_order_id"),
    )
