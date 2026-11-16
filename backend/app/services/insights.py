"""Explainable operational insights computed from the restaurant's own data.

No AI provider is involved. Every insight states the numbers behind it so
staff can check it, and links to the screen where they can act on it.

Stock-out risk (per ingredient, quantities in the base unit)::

    daily use      = forecast use over the next days (when a current forecast exists),
                     otherwise net sales use over the last 14 days / days since trading began
    days of cover  = current stock / daily use
    critical       = days of cover < supplier lead time        (an order placed now arrives too late)
    warning        = days of cover < lead time + 1 day, or stock at/below its reorder level
    out            = no stock left

An ingredient that is critical but already has stock on order is shown as a
warning, with the incoming quantity stated.
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.api.deps import RestaurantContext
from app.core.permissions import Permission
from app.forecasting.service import is_forecast_stale, open_days
from app.models import Forecast, ForecastRun, Ingredient, InventoryMovement, Order
from app.models.enums import ForecastTarget, MovementType, OrderStatus
from app.repositories.tenant import scoped
from app.schemas.analytics import Dashboard, ForecastSummary, Insight, StockRisk
from app.services import analytics, purchasing
from app.services.recommendations import supplier_terms
from app.services.units import format_quantity, quantize

USAGE_WINDOW_DAYS = 14
FORECAST_USE_DAYS = 7
WARNING_BUFFER_DAYS = 1  # the review period used by reorder suggestions
KITCHEN_WAIT_WARNING_MINUTES = 20
LEVEL_ORDER = {"out": 0, "critical": 1, "warning": 2, "ok": 3}
SEVERITY_ORDER = {"critical": 0, "warning": 1, "positive": 2, "info": 3}


# --------------------------------------------------------------------------- forecast freshness


def forecast_coverage(db: Session, run: ForecastRun) -> date | None:
    """Last date the run predicts."""
    return db.scalar(select(func.max(Forecast.forecast_date)).where(Forecast.run_id == run.id))


def _current_run(db: Session, ctx: RestaurantContext, today: date) -> ForecastRun | None:
    run = db.scalar(scoped(ForecastRun, ctx.restaurant_id).order_by(ForecastRun.created_at.desc()).limit(1))
    if run is None:
        return None
    created_on = analytics.local_date_of(ctx, run.created_at)
    return None if is_forecast_stale(created_on, forecast_coverage(db, run), today) else run


# --------------------------------------------------------------------------- stock-out risk


def _recent_daily_use(db: Session, ctx: RestaurantContext, today: date) -> dict[uuid.UUID, Decimal]:
    start, end = today - timedelta(days=USAGE_WINDOW_DAYS), today - timedelta(days=1)
    trading = open_days(db, ctx.restaurant_id, ctx.restaurant.timezone, start, end)
    if not trading:
        return {}
    # Per calendar day since trading began in the window, so closed days count as zero use.
    days = (end - min(trading)).days + 1
    lower, upper = analytics.utc_bounds_for(ctx.restaurant.timezone, start, end)
    rows = db.execute(
        select(InventoryMovement.ingredient_id, -func.sum(InventoryMovement.quantity))
        .where(
            InventoryMovement.restaurant_id == ctx.restaurant_id,
            InventoryMovement.movement_type.in_((MovementType.SALE, MovementType.SALE_REVERSAL)),
            InventoryMovement.created_at >= lower,
            InventoryMovement.created_at < upper,
        )
        .group_by(InventoryMovement.ingredient_id)
    ).all()
    return {i: q / days for i, q in rows if q and q > 0}


def _forecast_daily_use(db: Session, run: ForecastRun, today: date) -> dict[uuid.UUID, Decimal]:
    rows = db.execute(
        select(Forecast.ingredient_id, func.sum(Forecast.predicted_quantity), func.count())
        .where(
            Forecast.run_id == run.id,
            Forecast.target_type == ForecastTarget.INGREDIENT,
            Forecast.forecast_date >= today,
            Forecast.forecast_date < today + timedelta(days=FORECAST_USE_DAYS + 1),
        )
        .group_by(Forecast.ingredient_id)
    ).all()
    return {i: total / n for i, total, n in rows if i is not None and n and total is not None}


def stock_risks(db: Session, ctx: RestaurantContext) -> list[StockRisk]:
    """Every active ingredient with its days of cover and risk level, most urgent first."""
    today = analytics.local_today(ctx)
    ingredients = db.scalars(scoped(Ingredient, ctx.restaurant_id).where(Ingredient.is_active.is_(True))).all()
    if not ingredients:
        return []
    run = _current_run(db, ctx, today)
    forecast_use = _forecast_daily_use(db, run, today) if run else {}
    recent_use = _recent_daily_use(db, ctx, today)
    incoming = purchasing.incoming_quantities(db, ctx.restaurant_id)
    terms = supplier_terms(db, ctx.restaurant_id, ingredients)

    risks = []
    for ingredient in ingredients:
        unit = ingredient.base_unit.value
        stock = ingredient.current_stock
        supplier, lead_time, _, _ = terms[ingredient.id]
        on_order = quantize(incoming.get(ingredient.id, Decimal(0)))
        if ingredient.id in forecast_use:
            use, basis = forecast_use[ingredient.id], "forecast"
        elif ingredient.id in recent_use:
            use, basis = recent_use[ingredient.id], "recent_sales"
        else:
            use, basis = None, "none"
        cover = float(stock / use) if use and use > 0 and stock > 0 else None
        low = ingredient.reorder_level > 0 and stock <= ingredient.reorder_level

        if stock <= 0:
            level = "out"
        elif cover is not None and cover < lead_time:
            level = "warning" if on_order > 0 else "critical"
        elif (cover is not None and cover < lead_time + WARNING_BUFFER_DAYS) or low:
            level = "warning"
        else:
            level = "ok"

        basis_text = "forecast" if basis == "forecast" else "last 14 days"
        if stock <= 0:
            reason = "Out of stock."
        elif cover is not None:
            reason = (
                f"About {cover:.1f} day(s) left at {_rate(use, unit)}/day ({basis_text}); "
                f"lead time is {lead_time} day(s)."
            )
        elif low:
            reason = (
                f"At or below the reorder level ({format_quantity(ingredient.reorder_level, unit)}); "
                "no recent use to estimate how long it lasts."
            )
        else:
            reason = "No recent use."
        if on_order > 0:
            reason += f" {format_quantity(on_order, unit)} on order."

        risks.append(
            StockRisk(
                ingredient_id=ingredient.id,
                ingredient_name=ingredient.name,
                base_unit=unit,
                current_stock=stock,
                reorder_level=ingredient.reorder_level,
                incoming=on_order,
                daily_usage=quantize(use) if use is not None else None,
                usage_basis=basis,
                days_of_cover=round(cover, 1) if cover is not None else None,
                runs_out_on=today + timedelta(days=math.floor(cover)) if cover is not None else None,
                lead_time_days=lead_time,
                supplier_name=supplier.name if supplier else None,
                level=level,
                reason=reason,
            )
        )
    return sorted(
        risks,
        key=lambda r: (
            LEVEL_ORDER[r.level],
            r.days_of_cover if r.days_of_cover is not None else 1e9,
            r.ingredient_name,
        ),
    )


# --------------------------------------------------------------------------- insights


def _baht(minor: int) -> str:
    return f"฿{minor / 100:,.2f}"


def _duration(minutes: int) -> str:
    if minutes < 120:
        return f"{minutes} min"
    if minutes < 48 * 60:
        return f"{minutes // 60} hours"
    return f"{minutes // (24 * 60)} days"


def _names(items: list[str], limit: int = 3, total: int | None = None) -> str:
    total = len(items) if total is None else total
    shown = ", ".join(items[:limit])
    return f"{shown} and {total - min(limit, len(items))} more" if total > limit else shown


def _rate(value: Decimal, unit: str) -> str:
    """Daily use with sensible precision: 391.071 g -> 391 g, 28.96 -> 29.0, 0.456 -> 0.46."""
    step = Decimal("1") if value >= 100 else Decimal("0.1") if value >= 10 else Decimal("0.01")
    return format_quantity(value.quantize(step), unit)


def _sales_insight(dash: Dashboard) -> Insight | None:
    if not dash.comparison:
        return None
    cur, prev = dash.comparison.current, dash.comparison.previous
    if cur.order_count == 0:
        return Insight(
            key="sales-today",
            category="sales",
            severity="info",
            title="No paid orders yet today",
            detail="Today's sales appear here as orders are paid.",
            link="/pos",
            action="Open POS",
        )
    change = dash.comparison.net_sales_change_pct
    basis = f"{_baht(cur.net_sales_minor)} net from {cur.order_count} order(s)"
    if change is None:
        title, severity = f"Net sales {_baht(cur.net_sales_minor)} so far today", "info"
        detail = f"{basis}. There were no sales by this time yesterday to compare with."
    else:
        vs = f"{_baht(prev.net_sales_minor)} by this time yesterday"
        if change >= 10:
            title, severity = f"Sales are up {change:.0f}% on yesterday", "positive"
        elif change <= -15:
            title, severity = f"Sales are down {abs(change):.0f}% on yesterday", "warning"
        else:
            title, severity = f"Sales are in line with yesterday ({change:+.0f}%)", "info"
        detail = f"{basis}, against {vs}."
    if cur.average_order_value_minor:
        detail += f" Average order {_baht(cur.average_order_value_minor)}."
    return Insight(
        key="sales-today", category="sales", severity=severity, title=title, detail=detail, link="/analytics"
    )


def _stock_insight(risks: list[StockRisk]) -> Insight | None:
    urgent = [r for r in risks if r.level in ("out", "critical")]
    soon = [r for r in risks if r.level == "warning"]
    if urgent:
        out = [r.ingredient_name for r in urgent if r.level == "out"]
        critical = [r for r in urgent if r.level == "critical"]
        parts = []
        if out:
            parts.append(f"Out of stock: {_names(out)}.")
        if critical:
            first = critical[0]
            parts.append(
                f"{first.ingredient_name} lasts about {first.days_of_cover:.1f} day(s) but delivery takes "
                f"{first.lead_time_days} day(s)."
            )
            if len(critical) > 1:
                parts.append(f"Also at risk: {_names([r.ingredient_name for r in critical[1:]])}.")
        return Insight(
            key="stock-risk",
            category="inventory",
            severity="critical",
            title=f"{len(urgent)} ingredient(s) will run out before a delivery can arrive"
            if critical
            else f"{len(out)} ingredient(s) are out of stock",
            detail=" ".join(parts),
            link="/inventory",
            action="View stock",
        )
    if soon:
        return Insight(
            key="stock-risk",
            category="inventory",
            severity="warning",
            title=f"{len(soon)} ingredient(s) need reordering soon",
            detail=f"{_names([r.ingredient_name for r in soon])}. {soon[0].reason}",
            link="/inventory",
            action="View stock",
        )
    return None


def _forecast_insight(forecast: ForecastSummary | None, can_run: bool) -> Insight | None:
    if forecast is None:
        if not can_run:
            return None
        return Insight(
            key="forecast",
            category="forecast",
            severity="info",
            title="No demand forecast yet",
            detail="Run a forecast to predict tomorrow's demand and get reorder suggestions.",
            link="/forecasting",
            action="Run forecast",
        )
    if forecast.is_stale:
        until = f"{forecast.covers_until:%d %b}" if forecast.covers_until else "no future dates"
        return Insight(
            key="forecast",
            category="forecast",
            severity="warning",
            title="The demand forecast is out of date",
            detail=f"The latest forecast was made on {forecast.created_at:%d %b} and covers up to {until}. "
            "Reorder suggestions and stock-out estimates fall back to recent sales until it is re-run.",
            link="/forecasting",
            action="Run forecast" if can_run else "View forecast",
        )
    if not forecast.top_products:
        return None
    top = forecast.top_products[0]
    return Insight(
        key="forecast",
        category="forecast",
        severity="info",
        title=f"Expect about {float(forecast.total_predicted_items):.0f} items on {forecast.target_date:%a %d %b}",
        detail=f"Top item: about {float(top.predicted_quantity):.0f} x {top.product_name} "
        f"(model: {forecast.model_name}).",
        link="/forecasting",
    )


def _kitchen_insights(db: Session, ctx: RestaurantContext, dash: Dashboard) -> list[Insight]:
    out: list[Insight] = []
    if not dash.kitchen:
        return out
    oldest = db.scalar(
        select(func.min(Order.confirmed_at)).where(
            Order.restaurant_id == ctx.restaurant_id,
            Order.status.in_([OrderStatus.CONFIRMED, OrderStatus.PREPARING]),
        )
    )
    if oldest is not None:
        waited = int((datetime.now(UTC) - oldest).total_seconds() // 60)
        if waited >= KITCHEN_WAIT_WARNING_MINUTES:
            out.append(
                Insight(
                    key="kitchen-wait",
                    category="kitchen",
                    severity="warning",
                    title=f"The oldest kitchen ticket has waited {_duration(waited)}",
                    detail=f"{dash.kitchen.new} new and {dash.kitchen.preparing} in preparation.",
                    link="/kitchen",
                    action="Open kitchen",
                )
            )
    if dash.kitchen.ready:
        out.append(
            Insight(
                key="kitchen-ready",
                category="kitchen",
                severity="info",
                title=f"{dash.kitchen.ready} order(s) ready to serve",
                detail="Completed by the kitchen and waiting for pickup or service.",
                link="/kitchen" if ctx.can(Permission.KITCHEN_READ) else "/orders",
            )
        )
    return out


def _peak_hour_insight(db: Session, ctx: RestaurantContext, today: date) -> Insight | None:
    """Busiest hour on this weekday over the last four weeks."""
    tz = ctx.restaurant.timezone
    start = today - timedelta(days=28)
    lower, upper = analytics.utc_bounds_for(tz, start, today - timedelta(days=1))
    local = func.timezone(tz, Order.paid_at)
    rows = db.execute(
        select(cast(local, Date), func.extract("hour", local), func.count())
        .where(
            Order.restaurant_id == ctx.restaurant_id,
            Order.status != OrderStatus.CANCELLED,
            Order.payment_status.in_(analytics.SETTLED),
            Order.paid_at >= lower,
            Order.paid_at < upper,
            func.extract("isodow", local) == today.isoweekday(),
        )
        .group_by(cast(local, Date), func.extract("hour", local))
    ).all()
    days = {d for d, _, _ in rows}
    if len(days) < 2:
        return None
    by_hour: dict[int, int] = {}
    for _, hour, count in rows:
        by_hour[int(hour)] = by_hour.get(int(hour), 0) + int(count)
    hour, total = max(by_hour.items(), key=lambda kv: (kv[1], -kv[0]))
    average = total / len(days)
    weekday = f"{today:%A}s"
    now_hour = analytics.local_now(ctx).hour
    when = "is coming up" if now_hour < hour else "has passed" if now_hour > hour else "is now"
    return Insight(
        key="peak-hour",
        category="sales",
        severity="info",
        title=f"{weekday} peak: {hour:02d}:00–{(hour + 1) % 24:02d}:00 ({when})",
        detail=f"About {average:.0f} paid order(s) in that hour on average over the last {len(days)} {weekday}.",
        link="/analytics",
    )


def _menu_insight(db: Session, ctx: RestaurantContext, today: date) -> Insight | None:
    start, end = today - timedelta(days=USAGE_WINDOW_DAYS), today - timedelta(days=1)
    if len(open_days(db, ctx.restaurant_id, ctx.restaurant.timezone, start, end)) < 7:
        return None  # too little trading to call anything slow
    unsold = [
        p.product_name for p in analytics.slow_products(db, ctx, analytics.Filters(start, end), 50) if p.quantity == 0
    ]
    if not unsold:
        return None
    return Insight(
        key="menu-unsold",
        category="menu",
        severity="info",
        title=f"{len(unsold)} menu item(s) have not sold in {USAGE_WINDOW_DAYS} days",
        detail=f"{_names(unsold)}. Consider promoting, repricing or retiring them.",
        link="/menu",
        action="Review menu",
    )


def build_insights(db: Session, ctx: RestaurantContext, dash: Dashboard, risks: list[StockRisk]) -> list[Insight]:
    today = analytics.local_today(ctx)
    found: list[Insight | None] = [_sales_insight(dash)]
    if ctx.can(Permission.INVENTORY_READ):
        found.append(_stock_insight(risks))
    if ctx.can(Permission.RECOMMENDATIONS_READ) and dash.pending_recommendation_count:
        names = _names(
            [r.ingredient_name for r in dash.pending_recommendations], total=dash.pending_recommendation_count
        )
        found.append(
            Insight(
                key="reorders",
                category="inventory",
                severity="info",
                title=f"{dash.pending_recommendation_count} reorder suggestion(s) to review",
                detail=f"{names}. Approving creates draft purchase orders; nothing is sent automatically.",
                link="/forecasting?tab=recommendations",
                action="Review",
            )
        )
    found.extend(_kitchen_insights(db, ctx, dash))
    if ctx.can(Permission.FORECAST_READ):
        found.append(_forecast_insight(dash.forecast, ctx.can(Permission.FORECAST_RUN)))
    if ctx.can(Permission.ANALYTICS_READ):
        if dash.top_products_7_days:
            best = dash.top_products_7_days[0]
            found.append(
                Insight(
                    key="best-seller",
                    category="sales",
                    severity="info",
                    title=f"Best seller this week: {best.product_name}",
                    detail=f"{best.quantity} sold for {_baht(best.sales_minor)} over the last 7 days.",
                    link="/analytics",
                )
            )
        found.append(_peak_hour_insight(db, ctx, today))
        found.append(_menu_insight(db, ctx, today))
    insights = [i for i in found if i is not None]
    # Stable sort: urgent first, otherwise keep the order above.
    return sorted(insights, key=lambda i: SEVERITY_ORDER[i.severity])
