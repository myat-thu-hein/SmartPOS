"""Users, sessions, restaurants (tenants), memberships and audit logs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_col, str_enum, updated_at_col, uuid_pk
from app.models.enums import RestaurantRole


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    preferred_language: Mapped[str] = mapped_column(String(8), nullable=False, default="en", server_default="en")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    memberships: Mapped[list[RestaurantMembership]] = relationship(back_populates="user")

    __table_args__ = (
        # Emails are normalised to lower case by the service layer; the
        # functional index guarantees case-insensitive uniqueness regardless.
        Index("uq_users_email_lower", func.lower(email), unique=True),
    )


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = created_at_col()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))

    user: Mapped[User] = relationship()


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()


class Restaurant(Base):
    __tablename__ = "restaurants"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(200))
    branch_name: Mapped[str | None] = mapped_column(String(100))
    tax_id: Mapped[str | None] = mapped_column(String(32))
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(320))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="THB", server_default="THB")
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Asia/Bangkok", server_default="Asia/Bangkok"
    )
    locale: Mapped[str] = mapped_column(String(16), nullable=False, default="th-TH", server_default="th-TH")

    # Pricing rules. Rates are basis points (700 = 7.00 %).
    tax_rate_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=700, server_default="700")
    tax_label: Mapped[str] = mapped_column(String(32), nullable=False, default="VAT", server_default="VAT")
    prices_include_tax: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    service_charge_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    service_charge_taxable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    service_charge_dine_in_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    max_cashier_discount_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=1000, server_default="1000")

    # Inventory policy. Negative stock is only possible when a manager enables it.
    allow_negative_stock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    # Loyalty rules: earn 1 point per `loyalty_spend_per_point_minor` spent;
    # each redeemed point is worth `loyalty_point_value_minor`.
    loyalty_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    loyalty_spend_per_point_minor: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2500, server_default="2500"
    )
    loyalty_point_value_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=100, server_default="100")

    receipt_header: Mapped[str | None] = mapped_column(Text)
    receipt_footer: Mapped[str | None] = mapped_column(Text)
    order_number_prefix: Mapped[str] = mapped_column(String(8), nullable=False, default="", server_default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        CheckConstraint("tax_rate_bps >= 0 AND tax_rate_bps <= 5000", name="tax_rate_range"),
        CheckConstraint("service_charge_bps >= 0 AND service_charge_bps <= 5000", name="service_range"),
        CheckConstraint(
            "max_cashier_discount_bps >= 0 AND max_cashier_discount_bps <= 10000", name="cashier_discount_range"
        ),
        CheckConstraint("loyalty_spend_per_point_minor > 0", name="loyalty_spend_positive"),
        CheckConstraint("loyalty_point_value_minor >= 0", name="loyalty_value_nonnegative"),
    )


class RestaurantCounter(Base):
    """Per-restaurant sequences (order numbers, purchase order numbers)."""

    __tablename__ = "restaurant_counters"

    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), primary_key=True)
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class RestaurantMembership(Base):
    __tablename__ = "restaurant_memberships"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[RestaurantRole] = mapped_column(str_enum(RestaurantRole, 16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    user: Mapped[User] = relationship(back_populates="memberships")
    restaurant: Mapped[Restaurant] = relationship()

    __table_args__ = (UniqueConstraint("restaurant_id", "user_id"),)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("restaurants.id", ondelete="SET NULL"), index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("ix_audit_logs_created", "created_at"),)
