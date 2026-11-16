"""Analytics, dashboard and CSV reports."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import RestaurantContext, require
from app.core.permissions import Permission
from app.db.session import get_db
from app.models.enums import OrderType
from app.schemas.analytics import (
    CategorySales,
    Dashboard,
    DayBucket,
    HourBucket,
    IngredientUsage,
    PaymentShare,
    PeriodComparison,
    ProductSales,
    SalesSummary,
    SupplierSpend,
)
from app.services import analytics, reports
from app.services.dashboard import build_dashboard

router = APIRouter()
can_analyse = require(Permission.ANALYTICS_READ)
can_report = require(Permission.REPORTS_READ)


def filters(
    ctx: RestaurantContext = Depends(can_analyse),
    start_date: date | None = Query(None, description="Local start date (restaurant time zone). Default: 6 days ago"),
    end_date: date | None = Query(None, description="Local end date, inclusive. Default: today"),
    product_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    payment_method: str | None = Query(None, max_length=32, description="Payment method code, e.g. CASH"),
    order_type: OrderType | None = None,
) -> analytics.Filters:
    end = end_date or analytics.local_today(ctx)
    start = start_date or end - timedelta(days=6)
    analytics.validate_range(start, end)
    return analytics.Filters(start, end, product_id, category_id, payment_method, order_type)


@router.get(
    "/analytics/dashboard",
    response_model=Dashboard,
    tags=["analytics"],
    summary="Role-aware dashboard (sections depend on the caller's permissions)",
)
def dashboard(
    ctx: RestaurantContext = Depends(require(Permission.ORDERS_READ)), db: Session = Depends(get_db)
) -> Dashboard:
    return build_dashboard(db, ctx)


@router.get("/analytics/summary", response_model=SalesSummary, tags=["analytics"])
def summary(
    f: analytics.Filters = Depends(filters),
    ctx: RestaurantContext = Depends(can_analyse),
    db: Session = Depends(get_db),
) -> SalesSummary:
    return analytics.summary(db, ctx, f)


@router.get(
    "/analytics/comparison",
    response_model=PeriodComparison,
    tags=["analytics"],
    summary="Compare the range with the immediately preceding period of equal length",
)
def comparison(
    f: analytics.Filters = Depends(filters),
    ctx: RestaurantContext = Depends(can_analyse),
    db: Session = Depends(get_db),
) -> PeriodComparison:
    return analytics.comparison(db, ctx, f)


@router.get("/analytics/sales-by-hour", response_model=list[HourBucket], tags=["analytics"])
def by_hour(
    f: analytics.Filters = Depends(filters),
    ctx: RestaurantContext = Depends(can_analyse),
    db: Session = Depends(get_db),
) -> list[HourBucket]:
    return analytics.sales_by_hour(db, ctx, f)


@router.get("/analytics/sales-by-day", response_model=list[DayBucket], tags=["analytics"])
def by_day(
    f: analytics.Filters = Depends(filters),
    ctx: RestaurantContext = Depends(can_analyse),
    db: Session = Depends(get_db),
) -> list[DayBucket]:
    return analytics.sales_by_day(db, ctx, f)


@router.get("/analytics/sales-by-category", response_model=list[CategorySales], tags=["analytics"])
def by_category(
    f: analytics.Filters = Depends(filters),
    ctx: RestaurantContext = Depends(can_analyse),
    db: Session = Depends(get_db),
) -> list[CategorySales]:
    return analytics.sales_by_category(db, ctx, f)


@router.get("/analytics/top-products", response_model=list[ProductSales], tags=["analytics"])
def top_products(
    limit: int = Query(10, ge=1, le=100),
    f: analytics.Filters = Depends(filters),
    ctx: RestaurantContext = Depends(can_analyse),
    db: Session = Depends(get_db),
) -> list[ProductSales]:
    return analytics.top_products(db, ctx, f, limit)


@router.get("/analytics/slow-products", response_model=list[ProductSales], tags=["analytics"])
def slow_products(
    limit: int = Query(10, ge=1, le=100),
    f: analytics.Filters = Depends(filters),
    ctx: RestaurantContext = Depends(can_analyse),
    db: Session = Depends(get_db),
) -> list[ProductSales]:
    return analytics.slow_products(db, ctx, f, limit)


@router.get("/analytics/payment-distribution", response_model=list[PaymentShare], tags=["analytics"])
def payment_distribution(
    f: analytics.Filters = Depends(filters),
    ctx: RestaurantContext = Depends(can_analyse),
    db: Session = Depends(get_db),
) -> list[PaymentShare]:
    return analytics.payment_distribution(db, ctx, f)


@router.get("/analytics/ingredient-consumption", response_model=list[IngredientUsage], tags=["analytics"])
def ingredient_consumption(
    f: analytics.Filters = Depends(filters),
    ctx: RestaurantContext = Depends(can_analyse),
    db: Session = Depends(get_db),
) -> list[IngredientUsage]:
    return analytics.ingredient_consumption(db, ctx, f)


@router.get("/analytics/waste", response_model=list[IngredientUsage], tags=["analytics"])
def waste(
    f: analytics.Filters = Depends(filters),
    ctx: RestaurantContext = Depends(can_analyse),
    db: Session = Depends(get_db),
) -> list[IngredientUsage]:
    return analytics.waste(db, ctx, f)


@router.get("/analytics/purchases", response_model=list[SupplierSpend], tags=["analytics"])
def purchase_spend(
    f: analytics.Filters = Depends(filters),
    ctx: RestaurantContext = Depends(can_analyse),
    db: Session = Depends(get_db),
) -> list[SupplierSpend]:
    return analytics.purchases(db, ctx, f)


def _csv(content: str, name: str, f: analytics.Filters | None = None) -> Response:
    suffix = f"_{f.start_date}_{f.end_date}" if f else ""
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}{suffix}.csv"'},
    )


@router.get("/reports/daily-sales.csv", tags=["reports"], response_class=Response)
def daily_sales_report(
    f: analytics.Filters = Depends(filters), ctx: RestaurantContext = Depends(can_report), db: Session = Depends(get_db)
) -> Response:
    return _csv(reports.daily_sales_csv(db, ctx, f), "daily_sales", f)


@router.get("/reports/product-sales.csv", tags=["reports"], response_class=Response)
def product_sales_report(
    f: analytics.Filters = Depends(filters), ctx: RestaurantContext = Depends(can_report), db: Session = Depends(get_db)
) -> Response:
    return _csv(reports.product_sales_csv(db, ctx, f), "product_sales", f)


@router.get("/reports/orders.csv", tags=["reports"], response_class=Response)
def orders_report(
    f: analytics.Filters = Depends(filters), ctx: RestaurantContext = Depends(can_report), db: Session = Depends(get_db)
) -> Response:
    return _csv(reports.orders_csv(db, ctx, f), "orders", f)


@router.get("/reports/inventory-movements.csv", tags=["reports"], response_class=Response)
def movements_report(
    f: analytics.Filters = Depends(filters), ctx: RestaurantContext = Depends(can_report), db: Session = Depends(get_db)
) -> Response:
    return _csv(reports.inventory_movements_csv(db, ctx, f), "inventory_movements", f)


@router.get("/reports/inventory-valuation.csv", tags=["reports"], response_class=Response)
def valuation_report(ctx: RestaurantContext = Depends(can_report), db: Session = Depends(get_db)) -> Response:
    return _csv(reports.inventory_valuation_csv(db, ctx), "inventory_valuation")


@router.get("/reports/purchases.csv", tags=["reports"], response_class=Response)
def purchases_report(
    f: analytics.Filters = Depends(filters), ctx: RestaurantContext = Depends(can_report), db: Session = Depends(get_db)
) -> Response:
    return _csv(reports.purchases_csv(db, ctx, f), "purchases", f)
