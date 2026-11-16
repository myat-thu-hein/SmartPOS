"""Forecast runs, forecast values, model metrics and reorder recommendations."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import QTY, Base, created_at_col, str_enum, updated_at_col, uuid_pk
from app.models.enums import ForecastTarget, RecommendationStatus


class ForecastRun(Base):
    __tablename__ = "forecast_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False)
    model_name: Mapped[str] = mapped_column(String(50), nullable=False)
    model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    selection_strategy: Mapped[str] = mapped_column(String(20), nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    history_start: Mapped[date | None] = mapped_column(Date)
    history_end: Mapped[date | None] = mapped_column(Date)
    history_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    products_forecast: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    uses_demo_data: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at_col()

    metrics: Mapped[list[ForecastModelMetric]] = relationship(back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("horizon_days >= 1 AND horizon_days <= 28", name="horizon_range"),
        Index("ix_forecast_runs_time", "restaurant_id", "created_at"),
    )


class Forecast(Base):
    __tablename__ = "forecasts"

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("forecast_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False)
    target_type: Mapped[ForecastTarget] = mapped_column(str_enum(ForecastTarget, 16), nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    ingredient_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingredients.id", ondelete="CASCADE"))
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)
    horizon_day: Mapped[int] = mapped_column(Integer, nullable=False)
    predicted_quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    actual_quantity: Mapped[Decimal | None] = mapped_column(QTY)
    model_name: Mapped[str] = mapped_column(String(50), nullable=False)
    model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint("(product_id IS NOT NULL) <> (ingredient_id IS NOT NULL)", name="one_target"),
        CheckConstraint("predicted_quantity >= 0", name="prediction_nonnegative"),
        Index("ix_forecasts_target_date", "restaurant_id", "target_type", "forecast_date"),
        Index("ix_forecasts_product", "product_id", "forecast_date"),
        Index("ix_forecasts_ingredient", "ingredient_id", "forecast_date"),
    )


class ForecastModelMetric(Base):
    """Backtest metrics for one candidate model within a forecast run."""

    __tablename__ = "forecast_model_metrics"

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("forecast_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_name: Mapped[str] = mapped_column(String(50), nullable=False)
    model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    evaluation_points: Mapped[int] = mapped_column(Integer, nullable=False)
    mae: Mapped[float | None] = mapped_column(Float)
    rmse: Mapped[float | None] = mapped_column(Float)
    mape: Mapped[float | None] = mapped_column(Float)
    mape_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    zero_actual_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    is_selected: Mapped[bool] = mapped_column(nullable=False, default=False)

    run: Mapped[ForecastRun] = relationship(back_populates="metrics")


class ReorderRecommendation(Base):
    __tablename__ = "reorder_recommendations"

    id: Mapped[uuid.UUID] = uuid_pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    forecast_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("forecast_runs.id", ondelete="SET NULL"))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"))
    status: Mapped[RecommendationStatus] = mapped_column(
        str_enum(RecommendationStatus, 16), nullable=False, default=RecommendationStatus.PENDING
    )
    # Calculation inputs (base units of the ingredient).
    current_stock: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    forecast_demand: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    safety_stock: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    incoming_quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False)
    coverage_days: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    suggested_quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    approved_quantity: Mapped[Decimal | None] = mapped_column(QTY)
    min_order_quantity: Mapped[Decimal | None] = mapped_column(QTY)
    unit: Mapped[str] = mapped_column(String(8), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    calculation: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(String(500))
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("purchase_orders.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        CheckConstraint("suggested_quantity >= 0", name="suggested_nonnegative"),
        CheckConstraint("approved_quantity IS NULL OR approved_quantity >= 0", name="approved_nonnegative"),
        Index("ix_recommendations_status", "restaurant_id", "status"),
    )
