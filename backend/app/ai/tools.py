"""Approved business tools available to the AI assistant.

Each tool:
* validates its arguments with a Pydantic model,
* checks the caller's permission in the current restaurant,
* calls the same deterministic services the rest of the API uses, and
* returns compact JSON without customer personal data.

The language model never receives SQL access, credentials or raw tables.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RestaurantContext
from app.core.permissions import Permission
from app.forecasting import service as forecast_service
from app.models import Forecast, Product
from app.models.enums import ForecastTarget, RecommendationStatus
from app.services import analytics, inventory, recommendations

Period = Literal["today", "yesterday", "last_7_days", "this_week", "last_week", "this_month", "last_30_days"]
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def clean(text: str | None, limit: int = 80) -> str:
    """Neutralise untrusted strings (e.g. product names) before giving them to the model."""
    if not text:
        return ""
    return _CONTROL.sub(" ", text)[:limit]


def baht(minor: int | float | None) -> str:
    return f"฿{(minor or 0) / 100:,.2f}"


class PeriodArgs(BaseModel):
    period: Period | None = Field(default=None, description="Named period. Ignored when start_date is given.")
    start_date: date | None = Field(default=None, description="Inclusive local start date (YYYY-MM-DD)")
    end_date: date | None = Field(default=None, description="Inclusive local end date (YYYY-MM-DD)")

    @model_validator(mode="after")
    def _check(self) -> PeriodArgs:
        if self.start_date and self.end_date:
            analytics.validate_range(self.start_date, self.end_date)
        return self

    def resolve(self, today: date) -> tuple[date, date]:
        if self.start_date:
            return self.start_date, self.end_date or today
        period = self.period or "today"
        if period == "today":
            return today, today
        if period == "yesterday":
            y = today - timedelta(days=1)
            return y, y
        if period == "this_week":
            return today - timedelta(days=today.weekday()), today
        if period == "last_week":
            start = today - timedelta(days=today.weekday() + 7)
            return start, start + timedelta(days=6)
        if period == "this_month":
            return today.replace(day=1), today
        if period == "last_30_days":
            return today - timedelta(days=29), today
        return today - timedelta(days=6), today


class RankedArgs(PeriodArgs):
    limit: int = Field(default=5, ge=1, le=20)


class LimitArgs(BaseModel):
    limit: int = Field(default=10, ge=1, le=50)


class ForecastArgs(BaseModel):
    days: int = Field(default=1, ge=1, le=14, description="How many days ahead, starting tomorrow")
    product_name: str | None = Field(default=None, max_length=100, description="Optional product name filter")


class RecommendationArgs(BaseModel):
    status: Literal["PENDING", "APPROVED", "MODIFIED", "REJECTED", "COMPLETED"] = "PENDING"


class NoArgs(BaseModel):
    pass


def _range(ctx: RestaurantContext, args: PeriodArgs) -> analytics.Filters:
    start, end = args.resolve(analytics.local_today(ctx))
    analytics.validate_range(start, end)
    return analytics.Filters(start, end)


def get_sales_summary(db: Session, ctx: RestaurantContext, args: PeriodArgs) -> dict[str, Any]:
    f = _range(ctx, args)
    cmp = analytics.comparison(db, ctx, f)
    cur, prev = cmp.current, cmp.previous
    return {
        "kind": "historical",
        "date_range": {
            "start": f.start_date.isoformat(),
            "end": f.end_date.isoformat(),
            "timezone": ctx.restaurant.timezone,
            "until_time": cur.range.cutoff_time.strftime("%H:%M") if cur.range.cutoff_time else None,
        },
        "orders": cur.order_count,
        "items_sold": cur.items_sold,
        "gross_sales": baht(cur.gross_sales_minor),
        "discounts": baht(cur.discounts_minor),
        "refunds": baht(cur.refunds_minor),
        "net_sales": baht(cur.net_sales_minor),
        "tax": baht(cur.tax_minor),
        "service_charge": baht(cur.service_charge_minor),
        "total_collected": baht(cur.total_collected_minor),
        "average_order_value": baht(cur.average_order_value_minor),
        "previous_period": {
            "start": prev.range.start_date.isoformat(),
            "end": prev.range.end_date.isoformat(),
            "until_time": prev.range.cutoff_time.strftime("%H:%M") if prev.range.cutoff_time else None,
            "orders": prev.order_count,
            "net_sales": baht(prev.net_sales_minor),
        },
        "net_sales_change_pct": cmp.net_sales_change_pct,
        "order_count_change_pct": cmp.order_count_change_pct,
        "definitions": "net_sales = gross_sales - discounts - refunds; revenue is not profit. When until_time is set "
        "the period is still in progress and both periods are cut at that local time of day.",
    }


def _ranked(db: Session, ctx: RestaurantContext, args: RankedArgs, slow: bool) -> dict[str, Any]:
    f = _range(ctx, args)
    rows = (analytics.slow_products if slow else analytics.top_products)(db, ctx, f, args.limit)
    return {
        "kind": "historical",
        "date_range": {"start": f.start_date.isoformat(), "end": f.end_date.isoformat()},
        "products": [
            {
                "name": clean(r.product_name),
                "category": clean(r.category_name),
                "quantity": r.quantity,
                "sales": baht(r.sales_minor),
            }
            for r in rows
        ],
    }


def get_top_products(db: Session, ctx: RestaurantContext, args: RankedArgs) -> dict[str, Any]:
    return _ranked(db, ctx, args, slow=False)


def get_slow_products(db: Session, ctx: RestaurantContext, args: RankedArgs) -> dict[str, Any]:
    return _ranked(db, ctx, args, slow=True)


def get_inventory_status(db: Session, ctx: RestaurantContext, args: NoArgs) -> dict[str, Any]:
    s = inventory.summary(db, ctx)
    return {
        "kind": "current",
        "active_ingredients": s.ingredient_count,
        "low_stock": s.low_stock_count,
        "out_of_stock": s.out_of_stock_count,
        "stock_value": baht(s.total_value_minor),
        "ingredients_without_cost": s.unvalued_ingredient_count,
    }


def get_low_stock_items(db: Session, ctx: RestaurantContext, args: LimitArgs) -> dict[str, Any]:
    items = inventory.list_ingredients(db, ctx, search=None, low_stock_only=True, include_inactive=False)
    return {
        "kind": "current",
        "count": len(items),
        "items": [
            {
                "name": clean(i.name),
                "current_stock": float(i.current_stock),
                "reorder_level": float(i.reorder_level),
                "unit": i.base_unit.value,
            }
            for i in items[: args.limit]
        ],
    }


def get_forecast(db: Session, ctx: RestaurantContext, args: ForecastArgs) -> dict[str, Any]:
    run = forecast_service.latest_run(db, ctx)
    if run is None:
        return {"kind": "forecast", "available": False, "message": "No forecast has been generated yet."}
    start = analytics.local_today(ctx) + timedelta(days=1)
    end = start + timedelta(days=args.days - 1)
    stmt = (
        select(Product.name, Forecast.forecast_date, Forecast.predicted_quantity)
        .join(Product, Product.id == Forecast.product_id)
        .where(
            Forecast.run_id == run.id,
            Forecast.target_type == ForecastTarget.PRODUCT,
            Forecast.forecast_date >= start,
            Forecast.forecast_date <= end,
        )
    )
    if args.product_name:
        stmt = stmt.where(Product.name.ilike(f"%{args.product_name.strip()}%"))
    totals: dict[str, float] = {}
    for name, _, qty in db.execute(stmt).all():
        totals[clean(name)] = totals.get(clean(name), 0.0) + float(qty)
    ranked = sorted(totals.items(), key=lambda kv: -kv[1])[:15]
    return {
        "kind": "forecast",
        "available": bool(ranked),
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "model": run.model_name,
        "generated_at": run.created_at.isoformat(),
        "uses_demo_data": run.uses_demo_data,
        "warnings": [clean(w, 200) for w in (run.warnings or [])][:5],
        "products": [{"name": n, "predicted_quantity": round(q, 1)} for n, q in ranked],
        "note": "Predictions, not actual sales." if ranked else "The latest forecast does not cover these dates.",
    }


def get_reorder_recommendations(db: Session, ctx: RestaurantContext, args: RecommendationArgs) -> dict[str, Any]:
    recs = recommendations.list_recommendations(db, ctx, [RecommendationStatus(args.status)])
    return {
        "kind": "recommendation",
        "status": args.status,
        "count": len(recs),
        "items": [
            {
                "ingredient": clean(r.ingredient_name),
                "suggested_quantity": float(r.suggested_quantity),
                "unit": r.unit,
                "supplier": clean(r.supplier_name),
                "reason": clean(r.reason, 400),
            }
            for r in recs[:15]
        ],
        "note": "Recommendations require explicit manager approval in SmartPOS; nothing is ordered automatically.",
    }


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    permission: Permission
    handler: Callable[[Session, RestaurantContext, Any], dict[str, Any]]

    def schema(self) -> dict[str, Any]:
        params = self.args_model.model_json_schema()
        params.pop("title", None)
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": params},
        }


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in (
        Tool(
            "get_sales_summary",
            "Sales totals for a period (orders, gross/net sales, discounts, refunds, tax) with a "
            "comparison against the previous period of the same length.",
            PeriodArgs,
            Permission.ANALYTICS_READ,
            get_sales_summary,
        ),
        Tool(
            "get_top_products",
            "Best-selling products by quantity for a period.",
            RankedArgs,
            Permission.ANALYTICS_READ,
            get_top_products,
        ),
        Tool(
            "get_slow_products",
            "Slowest-selling active products for a period (including zero sales).",
            RankedArgs,
            Permission.ANALYTICS_READ,
            get_slow_products,
        ),
        Tool(
            "get_inventory_status",
            "Current inventory overview: counts of low and out-of-stock ingredients and stock value.",
            NoArgs,
            Permission.INVENTORY_READ,
            get_inventory_status,
        ),
        Tool(
            "get_low_stock_items",
            "Ingredients at or below their reorder level.",
            LimitArgs,
            Permission.INVENTORY_READ,
            get_low_stock_items,
        ),
        Tool(
            "get_forecast",
            "Predicted product demand from the latest forecast run, starting tomorrow.",
            ForecastArgs,
            Permission.FORECAST_READ,
            get_forecast,
        ),
        Tool(
            "get_reorder_recommendations",
            "Inventory reorder recommendations and their explanations.",
            RecommendationArgs,
            Permission.RECOMMENDATIONS_READ,
            get_reorder_recommendations,
        ),
    )
}


class ToolError(Exception):
    pass


def tools_for(ctx: RestaurantContext) -> list[Tool]:
    return [t for t in TOOLS.values() if ctx.can(t.permission)]


def execute(db: Session, ctx: RestaurantContext, name: str, raw_args: dict[str, Any]) -> dict[str, Any]:
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolError(f"Unknown tool '{name}'.")
    if not ctx.can(tool.permission):
        raise ToolError(f"Permission denied for {name}.")
    try:
        args = tool.args_model.model_validate(raw_args or {})
    except ValidationError as exc:
        raise ToolError(f"Invalid arguments for {name}: {exc.errors(include_url=False)[:3]}") from exc
    try:
        return tool.handler(db, ctx, args)
    except Exception as exc:
        message = getattr(exc, "message", None) or "the tool failed"
        raise ToolError(f"{name} could not run: {message}") from exc
