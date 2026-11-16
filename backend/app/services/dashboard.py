"""Role-aware dashboard aggregating real data from the other services."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import RestaurantContext
from app.core.permissions import Permission
from app.models import DiningTable, Forecast, ForecastRun, Ingredient, Order, Product, ReorderRecommendation
from app.models.enums import ForecastTarget, OrderStatus, RecommendationStatus
from app.repositories.tenant import scoped
from app.schemas.analytics import (
    Dashboard,
    ForecastHighlight,
    ForecastSummary,
    KitchenCounts,
    LowStockItem,
    PendingRecommendation,
    RecentOrder,
)
from app.services import analytics, insights
from app.services.tables import display_number


def build_dashboard(db: Session, ctx: RestaurantContext) -> Dashboard:
    today = analytics.local_today(ctx)
    dash = Dashboard(generated_at=datetime.now(UTC), timezone=ctx.restaurant.timezone)
    if ctx.can(Permission.ANALYTICS_READ):
        today_f = analytics.Filters(today, today)
        dash.comparison = analytics.comparison(db, ctx, today_f)
        dash.today = dash.comparison.current
        dash.sales_last_14_days = analytics.sales_by_day(db, ctx, analytics.Filters(today - timedelta(days=13), today))
        dash.sales_by_hour_today = analytics.sales_by_hour(db, ctx, today_f)
        dash.top_products_7_days = analytics.top_products(
            db, ctx, analytics.Filters(today - timedelta(days=6), today), limit=5
        )
    if ctx.can(Permission.ORDERS_READ):
        orders = db.scalars(scoped(Order, ctx.restaurant_id).order_by(Order.created_at.desc()).limit(8)).all()
        tables = dict(
            db.execute(
                select(DiningTable.id, DiningTable.name).where(DiningTable.restaurant_id == ctx.restaurant_id)
            ).all()
        )
        dash.recent_orders = [
            RecentOrder(
                id=o.id,
                display_number=display_number(ctx.restaurant.order_number_prefix, o.order_number),
                order_type=o.order_type.value,
                status=o.status.value,
                payment_status=o.payment_status.value,
                total_minor=o.total_minor,
                created_at=o.created_at,
                table_name=tables.get(o.table_id),
            )
            for o in orders
        ]
    if ctx.can(Permission.KITCHEN_READ):
        counts = dict(
            db.execute(
                select(Order.status, func.count())
                .where(
                    Order.restaurant_id == ctx.restaurant_id,
                    Order.status.in_([OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.READY]),
                )
                .group_by(Order.status)
            ).all()
        )
        dash.kitchen = KitchenCounts(
            new=counts.get(OrderStatus.CONFIRMED, 0),
            preparing=counts.get(OrderStatus.PREPARING, 0),
            ready=counts.get(OrderStatus.READY, 0),
        )
    if ctx.can(Permission.INVENTORY_READ):
        low = db.scalars(
            scoped(Ingredient, ctx.restaurant_id)
            .where(Ingredient.is_active.is_(True), Ingredient.current_stock <= Ingredient.reorder_level)
            .order_by(Ingredient.current_stock - Ingredient.reorder_level)
            .limit(8)
        ).all()
        dash.low_stock = [
            LowStockItem(
                id=i.id,
                name=i.name,
                base_unit=i.base_unit.value,
                current_stock=i.current_stock,
                reorder_level=i.reorder_level,
            )
            for i in low
        ]
    if ctx.can(Permission.FORECAST_READ):
        dash.forecast = latest_forecast_summary(db, ctx)
    if ctx.can(Permission.RECOMMENDATIONS_READ):
        pending = db.execute(
            select(ReorderRecommendation, Ingredient.name)
            .join(Ingredient, Ingredient.id == ReorderRecommendation.ingredient_id)
            .where(
                ReorderRecommendation.restaurant_id == ctx.restaurant_id,
                ReorderRecommendation.status == RecommendationStatus.PENDING,
            )
            .order_by(ReorderRecommendation.created_at.desc())
        ).all()
        dash.pending_recommendation_count = len(pending)
        dash.pending_recommendations = [
            PendingRecommendation(
                id=r.id,
                ingredient_name=name,
                suggested_quantity=r.suggested_quantity,
                unit=r.unit,
                created_at=r.created_at,
            )
            for r, name in pending[:5]
        ]
    risks = insights.stock_risks(db, ctx) if ctx.can(Permission.INVENTORY_READ) else []
    at_risk = [r for r in risks if r.level != "ok"]
    dash.stock_at_risk = at_risk[:6]
    dash.stock_at_risk_count = len(at_risk)
    dash.stock_critical_count = sum(r.level in ("out", "critical") for r in at_risk)
    dash.insights = insights.build_insights(db, ctx, dash, risks)
    return dash


def latest_forecast_summary(db: Session, ctx: RestaurantContext) -> ForecastSummary | None:
    run = db.scalar(scoped(ForecastRun, ctx.restaurant_id).order_by(ForecastRun.created_at.desc()).limit(1))
    if run is None:
        return None
    tomorrow = analytics.local_today(ctx) + timedelta(days=1)
    target = tomorrow
    rows = db.execute(
        select(Product.name, Forecast.predicted_quantity)
        .join(Product, Product.id == Forecast.product_id)
        .where(
            Forecast.run_id == run.id, Forecast.target_type == ForecastTarget.PRODUCT, Forecast.forecast_date == target
        )
        .order_by(Forecast.predicted_quantity.desc())
    ).all()
    if not rows:
        first = db.scalar(select(func.min(Forecast.forecast_date)).where(Forecast.run_id == run.id))
        if first is None:
            return None
        target = first
        rows = db.execute(
            select(Product.name, Forecast.predicted_quantity)
            .join(Product, Product.id == Forecast.product_id)
            .where(
                Forecast.run_id == run.id,
                Forecast.target_type == ForecastTarget.PRODUCT,
                Forecast.forecast_date == target,
            )
            .order_by(Forecast.predicted_quantity.desc())
        ).all()
    covers_until = insights.forecast_coverage(db, run)
    stale = insights.is_forecast_stale(
        analytics.local_date_of(ctx, run.created_at), covers_until, analytics.local_today(ctx)
    )
    return ForecastSummary(
        covers_until=covers_until,
        is_stale=stale,
        run_id=run.id,
        model_name=run.model_name,
        created_at=run.created_at,
        target_date=target,
        total_predicted_items=sum((q for _, q in rows), start=0),
        top_products=[ForecastHighlight(product_name=n, predicted_quantity=q) for n, q in rows[:5]],
        uses_demo_data=run.uses_demo_data,
        warnings=list(run.warnings or [])[:5],
    )
