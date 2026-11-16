"""Customers and the loyalty points ledger."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, str_enum, updated_at_col, uuid_pk
from app.models.enums import LoyaltyTransactionType


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    # Normalised to digits with an optional leading "+".
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(320))
    notes: Mapped[str | None] = mapped_column(Text)
    # Cached balance, always updated together with a loyalty transaction.
    loyalty_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        UniqueConstraint("restaurant_id", "phone"),
        CheckConstraint("loyalty_balance >= 0", name="balance_nonnegative"),
    )


class LoyaltyTransaction(Base):
    __tablename__ = "loyalty_transactions"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"))
    transaction_type: Mapped[LoyaltyTransactionType] = mapped_column(
        str_enum(LoyaltyTransactionType, 16), nullable=False
    )
    # Signed: positive adds points, negative removes them.
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(300))
    related_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("loyalty_transactions.id", ondelete="SET NULL")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint("points <> 0", name="points_nonzero"),
        Index("ix_loyalty_customer_time", "customer_id", "created_at"),
        # An order can earn points once and redeem points once.
        Index(
            "uq_loyalty_order_earn_redeem",
            "order_id",
            "transaction_type",
            unique=True,
            postgresql_where=text("transaction_type IN ('EARN', 'REDEEM') AND order_id IS NOT NULL"),
        ),
    )
