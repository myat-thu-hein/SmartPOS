"""Forecast and reorder recommendation schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import RecommendationStatus
from app.schemas.common import ORMModel, RequestModel
from app.utils.types import OptionalQty, PositiveQtyIn, Qty


class ModelInfo(BaseModel):
    name: str
    label: str
    description: str
    min_history_days: int


class ForecastRunCreate(RequestModel):
    horizon_days: int = Field(default=7, ge=1, le=14)
    model: str = Field(default="auto", description="'auto' selects the model with the lowest backtest MAE")
    history_days: int = Field(default=180, ge=14, le=730)
    eval_days: int = Field(default=14, ge=3, le=60)


class MetricOut(ORMModel):
    model_name: str
    model_version: str
    evaluation_points: int
    mae: float | None
    rmse: float | None
    mape: float | None
    mape_points: int
    zero_actual_points: int
    notes: str | None
    is_selected: bool


class ForecastPoint(BaseModel):
    date: date
    horizon_day: int
    predicted_quantity: Qty
    actual_quantity: OptionalQty


class ProductForecast(BaseModel):
    product_id: uuid.UUID
    product_name: str
    model_name: str
    total_predicted: Qty
    points: list[ForecastPoint]


class IngredientForecast(BaseModel):
    ingredient_id: uuid.UUID
    ingredient_name: str
    base_unit: str
    total_predicted: Qty
    points: list[ForecastPoint]


class ForecastRunSummary(ORMModel):
    id: uuid.UUID
    model_name: str
    model_version: str
    selection_strategy: str
    horizon_days: int
    history_start: date | None
    history_end: date | None
    history_days: int
    products_forecast: int
    warnings: list[str]
    uses_demo_data: bool
    created_at: datetime


class ForecastRunOut(ForecastRunSummary):
    parameters: dict[str, Any]
    metrics: list[MetricOut]
    # Last predicted date; a run that no longer predicts tomorrow, or is over a week old, is stale.
    covers_until: date | None = None
    is_stale: bool = False
    products: list[ProductForecast] = Field(default_factory=list)
    ingredients: list[IngredientForecast] = Field(default_factory=list)


class HistoryPoint(BaseModel):
    date: date
    actual_quantity: float | None
    predicted_quantity: float | None
    is_future: bool
    closed: bool = False


class ProductHistory(BaseModel):
    product_id: uuid.UUID
    product_name: str
    run_id: uuid.UUID | None
    model_name: str | None
    points: list[HistoryPoint]


class RecommendationGenerate(RequestModel):
    forecast_run_id: uuid.UUID | None = Field(default=None, description="Defaults to the latest forecast run")
    review_period_days: int = Field(
        default=3, ge=1, le=28, description="Days until the next planned ordering opportunity"
    )


class RecommendationOut(ORMModel):
    id: uuid.UUID
    ingredient_id: uuid.UUID
    ingredient_name: str | None = None
    supplier_id: uuid.UUID | None
    supplier_name: str | None = None
    forecast_run_id: uuid.UUID | None
    status: RecommendationStatus
    current_stock: Qty
    forecast_demand: Qty
    safety_stock: Qty
    incoming_quantity: Qty
    lead_time_days: int
    coverage_days: int
    raw_quantity: Qty
    suggested_quantity: Qty
    approved_quantity: OptionalQty
    min_order_quantity: OptionalQty
    unit: str
    reason: str
    calculation: dict[str, Any]
    reviewed_by: uuid.UUID | None
    reviewer_name: str | None = None
    reviewed_at: datetime | None
    review_note: str | None
    purchase_order_id: uuid.UUID | None
    created_at: datetime


class ReviewNote(RequestModel):
    note: str | None = Field(default=None, max_length=500)


class ModifyRecommendation(RequestModel):
    quantity: PositiveQtyIn
    unit: str | None = Field(default=None, max_length=20)
    note: str | None = Field(default=None, max_length=500)


class CreatePurchaseOrders(RequestModel):
    recommendation_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


class GenerateResult(BaseModel):
    forecast_run_id: uuid.UUID
    created: list[RecommendationOut]
    superseded: int
    skipped_without_need: int
    notes: list[str]


class PurchaseOrderCreated(BaseModel):
    purchase_order_id: uuid.UUID
    display_number: str
    supplier_name: str
    recommendation_ids: list[uuid.UUID]
