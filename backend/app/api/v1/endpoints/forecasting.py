"""Demand forecasting and reorder recommendations."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import RestaurantContext, require
from app.core.errors import NotFound
from app.core.permissions import Permission
from app.db.session import get_db
from app.forecasting import service as forecast_service
from app.models.enums import RecommendationStatus
from app.schemas.forecast import (
    CreatePurchaseOrders,
    ForecastRunCreate,
    ForecastRunOut,
    ForecastRunSummary,
    GenerateResult,
    ModelInfo,
    ModifyRecommendation,
    ProductHistory,
    PurchaseOrderCreated,
    RecommendationGenerate,
    RecommendationOut,
    ReviewNote,
)
from app.services import recommendations as rec_service

router = APIRouter()
can_read = require(Permission.FORECAST_READ)
can_review = require(Permission.RECOMMENDATIONS_REVIEW)


@router.get("/forecast/models", response_model=list[ModelInfo], tags=["forecast"])
def list_models(_: RestaurantContext = Depends(can_read)) -> list[ModelInfo]:
    return forecast_service.available_models()


@router.post(
    "/forecast/runs",
    response_model=ForecastRunOut,
    status_code=status.HTTP_201_CREATED,
    tags=["forecast"],
    summary="Backtest the models and generate a forecast",
)
def create_run(
    data: ForecastRunCreate,
    ctx: RestaurantContext = Depends(require(Permission.FORECAST_RUN)),
    db: Session = Depends(get_db),
) -> ForecastRunOut:
    return forecast_service.run_forecast(db, ctx, data)


@router.get("/forecast/runs", response_model=list[ForecastRunSummary], tags=["forecast"])
def list_runs(
    limit: int = Query(20, ge=1, le=100), ctx: RestaurantContext = Depends(can_read), db: Session = Depends(get_db)
) -> list[ForecastRunSummary]:
    return forecast_service.list_runs(db, ctx, limit)


@router.get("/forecast/latest", response_model=ForecastRunOut, tags=["forecast"])
def latest(ctx: RestaurantContext = Depends(can_read), db: Session = Depends(get_db)) -> ForecastRunOut:
    run = forecast_service.latest_run(db, ctx)
    if run is None:
        raise NotFound("No forecast has been generated yet.", code="no_forecast")
    return forecast_service.get_run(db, ctx, run.id)


@router.get("/forecast/runs/{run_id}", response_model=ForecastRunOut, tags=["forecast"])
def get_run(
    run_id: uuid.UUID, ctx: RestaurantContext = Depends(can_read), db: Session = Depends(get_db)
) -> ForecastRunOut:
    return forecast_service.get_run(db, ctx, run_id)


@router.get(
    "/forecast/products/{product_id}/history",
    response_model=ProductHistory,
    tags=["forecast"],
    summary="Actual daily sales versus predictions, plus the latest future forecast",
)
def product_history(
    product_id: uuid.UUID,
    days: int = Query(28, ge=7, le=180),
    ctx: RestaurantContext = Depends(can_read),
    db: Session = Depends(get_db),
) -> ProductHistory:
    return forecast_service.product_history(db, ctx, product_id, days)


@router.post("/recommendations/generate", response_model=GenerateResult, tags=["recommendations"])
def generate(
    data: RecommendationGenerate, ctx: RestaurantContext = Depends(can_review), db: Session = Depends(get_db)
) -> GenerateResult:
    return rec_service.generate(db, ctx, data)


@router.get("/recommendations", response_model=list[RecommendationOut], tags=["recommendations"])
def list_recommendations(
    status_filter: list[RecommendationStatus] | None = Query(None, alias="status"),
    ctx: RestaurantContext = Depends(require(Permission.RECOMMENDATIONS_READ)),
    db: Session = Depends(get_db),
) -> list[RecommendationOut]:
    return rec_service.list_recommendations(db, ctx, status_filter)


@router.post("/recommendations/{rec_id}/approve", response_model=RecommendationOut, tags=["recommendations"])
def approve(
    rec_id: uuid.UUID, data: ReviewNote, ctx: RestaurantContext = Depends(can_review), db: Session = Depends(get_db)
) -> RecommendationOut:
    return rec_service.approve(db, ctx, rec_id, data.note)


@router.post("/recommendations/{rec_id}/modify", response_model=RecommendationOut, tags=["recommendations"])
def modify(
    rec_id: uuid.UUID,
    data: ModifyRecommendation,
    ctx: RestaurantContext = Depends(can_review),
    db: Session = Depends(get_db),
) -> RecommendationOut:
    return rec_service.modify(db, ctx, rec_id, data)


@router.post("/recommendations/{rec_id}/reject", response_model=RecommendationOut, tags=["recommendations"])
def reject(
    rec_id: uuid.UUID, data: ReviewNote, ctx: RestaurantContext = Depends(can_review), db: Session = Depends(get_db)
) -> RecommendationOut:
    return rec_service.reject(db, ctx, rec_id, data.note)


@router.post(
    "/recommendations/purchase-orders",
    response_model=list[PurchaseOrderCreated],
    tags=["recommendations"],
    summary="Create DRAFT purchase orders from approved recommendations (never submitted automatically)",
)
def to_purchase_orders(
    data: CreatePurchaseOrders,
    ctx: RestaurantContext = Depends(require(Permission.RECOMMENDATIONS_REVIEW, Permission.PURCHASING_WRITE)),
    db: Session = Depends(get_db),
) -> list[PurchaseOrderCreated]:
    return rec_service.create_purchase_orders(db, ctx, data)
