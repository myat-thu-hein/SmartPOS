"""Forecast runs: data preparation, model selection, storage and actuals.

Data preparation
----------------
* Daily quantities per product come from eligible (paid, non-cancelled) orders,
  bucketed by the restaurant's local date.
* History ends yesterday (only complete days are used). Forecasts cover the
  days starting tomorrow.
* A day on which the restaurant recorded no paid orders at all is treated as
  closed (missing), not as zero demand. A day when the restaurant traded but a
  product did not sell is a genuine zero.
* No sales history is ever invented. Demo restaurants are flagged so their
  forecasts are labelled as based on synthetic data.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import numpy as np
from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.api.deps import RestaurantContext
from app.core.errors import NotFound, ValidationFailed
from app.forecasting import models
from app.forecasting.evaluation import Series, backtest
from app.models import (
    Forecast,
    ForecastModelMetric,
    ForecastRun,
    Ingredient,
    InventoryMovement,
    Order,
    Product,
)
from app.models.enums import ForecastTarget, MovementType, OrderStatus
from app.repositories.tenant import get_owned, scoped
from app.schemas.forecast import (
    ForecastPoint,
    ForecastRunCreate,
    ForecastRunOut,
    ForecastRunSummary,
    HistoryPoint,
    IngredientForecast,
    MetricOut,
    ModelInfo,
    ProductForecast,
    ProductHistory,
)
from app.services import analytics, realtime
from app.services.audit import record_audit
from app.services.recipes import active_recipes, effective_quantity

QTY = Decimal("0.001")
MIN_TOTAL_HISTORY_WARNING = 28


def available_models() -> list[ModelInfo]:
    return [
        ModelInfo(name=c.name, label=c.label, description=c.description, min_history_days=c.min_history)
        for c in (models.MODEL_CLASSES[n] for n in models.SELECTION_ORDER)
    ]


def _q(value: float) -> Decimal:
    return Decimal(str(max(value, 0.0))).quantize(QTY, ROUND_HALF_UP)


def open_days(db: Session, restaurant_id: uuid.UUID, timezone: str, start: date, end: date) -> set[date]:
    lower, upper = analytics.utc_bounds_for(timezone, start, end)
    day = cast(func.timezone(timezone, Order.paid_at), Date)
    rows = db.execute(
        select(day)
        .where(
            Order.restaurant_id == restaurant_id,
            Order.status != OrderStatus.CANCELLED,
            Order.payment_status.in_(analytics.SETTLED),
            Order.paid_at >= lower,
            Order.paid_at < upper,
        )
        .distinct()
    ).all()
    return {r[0] for r in rows}


def build_series(db: Session, ctx: RestaurantContext, start: date, end: date) -> tuple[list[Series], set[date]]:
    """Daily quantity series for active products that sold at least once."""
    timezone = ctx.restaurant.timezone
    rows = analytics.daily_product_quantities(db, ctx.restaurant_id, timezone, start, end)
    trading = open_days(db, ctx.restaurant_id, timezone, start, end)
    if not rows:
        return [], trading
    active = set(
        db.scalars(
            select(Product.id).where(Product.restaurant_id == ctx.restaurant_id, Product.is_active.is_(True))
        ).all()
    )
    by_product: dict[uuid.UUID, dict[date, int]] = defaultdict(dict)
    for product_id, day, qty in rows:
        if product_id in active:
            by_product[product_id][day] = qty
    series = []
    for product_id, days in by_product.items():
        first = min(days)
        length = (end - first).days + 1
        values = np.full(length, np.nan)
        for i in range(length):
            d = first + timedelta(days=i)
            if d in trading:
                values[i] = days.get(d, 0)
        series.append(Series(key=str(product_id), start=first, values=values))
    return series, trading


def _choose_model(name: str, series: Series) -> str:
    """Use the requested model if the product has enough history, else fall back."""
    obs = len(models.observed(series.values))
    chain = [name, *[m for m in models.FALLBACK_CHAIN if m != name]]
    for candidate in chain:
        if obs >= models.MODEL_CLASSES[candidate].min_history:
            return candidate
    return "moving_average"


def run_forecast(db: Session, ctx: RestaurantContext, data: ForecastRunCreate) -> ForecastRunOut:
    if data.model != "auto" and data.model not in models.MODEL_CLASSES:
        raise ValidationFailed(f"Unknown model '{data.model}'.", details={"available": list(models.MODEL_CLASSES)})
    today = analytics.local_today(ctx)
    history_end = today - timedelta(days=1)
    history_start = history_end - timedelta(days=data.history_days - 1)
    series, trading = build_series(db, ctx, history_start, history_end)
    if not series:
        raise ValidationFailed(
            "There is no sales history in the selected period, so no forecast can be made. "
            "Record some paid orders first.",
            code="insufficient_data",
        )
    warnings: list[str] = []
    trading_days = len(trading)
    if trading_days < MIN_TOTAL_HISTORY_WARNING:
        warnings.append(
            f"Only {trading_days} trading day(s) of history are available; forecasts are unreliable "
            f"until at least {MIN_TOTAL_HISTORY_WARNING} days have been recorded."
        )
    if ctx.restaurant.is_demo:
        warnings.append("This restaurant uses synthetic demo sales data; forecasts are for demonstration only.")

    # Stage 2/3: evaluate every model with enough history on the same rolling-origin backtest.
    results = {}
    for name in models.SELECTION_ORDER:
        if any(len(models.observed(s.values)) >= models.MODEL_CLASSES[name].min_history for s in series):
            results[name] = backtest(name, series, data.horizon_days, data.eval_days)
    scored = {n: r for n, r in results.items() if r.mae is not None}
    if data.model == "auto":
        if scored:
            selected = min(scored, key=lambda n: (scored[n].mae, models.SELECTION_ORDER.index(n)))
        else:
            selected = "moving_average"
            warnings.append("Not enough history to backtest any model; using a moving average.")
    else:
        selected = data.model
        if selected not in scored:
            warnings.append(f"{selected} could not be evaluated on this history; its accuracy is unknown.")

    run = ForecastRun(
        restaurant_id=ctx.restaurant_id,
        model_name=selected,
        model_version=models.MODEL_CLASSES[selected].version,
        selection_strategy="auto" if data.model == "auto" else "manual",
        horizon_days=data.horizon_days,
        history_start=min(s.start for s in series),
        history_end=history_end,
        history_days=trading_days,
        warnings=warnings,
        uses_demo_data=ctx.restaurant.is_demo,
        created_by=ctx.user_id,
        parameters={
            "history_days": data.history_days,
            "eval_days": data.eval_days,
            "requested_model": data.model,
            "metric_for_selection": "MAE",
            "validation": "rolling-origin backtest",
        },
    )
    db.add(run)
    db.flush()
    for name, result in results.items():
        db.add(
            ForecastModelMetric(
                run_id=run.id,
                model_name=name,
                model_version=models.MODEL_CLASSES[name].version,
                evaluation_points=result.points,
                mae=result.mae,
                rmse=result.rmse,
                mape=result.mape,
                mape_points=result.mape_points,
                zero_actual_points=result.zero_actual_points,
                notes=result.note,
                is_selected=name == selected,
            )
        )

    horizons = list(range(1, data.horizon_days + 1))
    # History ends yesterday; horizon 1 (tomorrow) is two days after the last history day.
    offsets = [(today - history_end).days + h for h in horizons]
    forecast_dates = [today + timedelta(days=h) for h in horizons]
    product_predictions: dict[uuid.UUID, list[float]] = {}
    fallbacks = 0
    for s in series:
        model_name = _choose_model(selected, s)
        fallbacks += model_name != selected
        model = models.create(model_name).fit(s.start, s.values)
        preds = model.predict(offsets)
        product_id = uuid.UUID(s.key)
        product_predictions[product_id] = list(preds)
        for h, d, p in zip(horizons, forecast_dates, preds, strict=True):
            db.add(
                Forecast(
                    run_id=run.id,
                    restaurant_id=ctx.restaurant_id,
                    target_type=ForecastTarget.PRODUCT,
                    product_id=product_id,
                    forecast_date=d,
                    horizon_day=h,
                    predicted_quantity=_q(p),
                    model_name=model_name,
                    model_version=model.version,
                )
            )
    if fallbacks:
        warnings.append(f"{fallbacks} product(s) had too little history for {selected} and used a simpler model.")

    # Ingredient demand = product forecast x current recipe (incl. waste factor).
    recipes = active_recipes(db, ctx.restaurant_id, set(product_predictions))
    ingredient_demand: dict[uuid.UUID, list[Decimal]] = defaultdict(lambda: [Decimal(0)] * len(horizons))
    for product_id, preds in product_predictions.items():
        recipe = recipes.get(product_id)
        if recipe is None:
            continue
        for item in recipe.items:
            per_serving = effective_quantity(item)
            for i, p in enumerate(preds):
                ingredient_demand[item.ingredient_id][i] += _q(p) * per_serving
    for ingredient_id, values in ingredient_demand.items():
        for h, d, v in zip(horizons, forecast_dates, values, strict=True):
            db.add(
                Forecast(
                    run_id=run.id,
                    restaurant_id=ctx.restaurant_id,
                    target_type=ForecastTarget.INGREDIENT,
                    ingredient_id=ingredient_id,
                    forecast_date=d,
                    horizon_day=h,
                    predicted_quantity=v.quantize(QTY, ROUND_HALF_UP),
                    model_name=selected,
                    model_version=run.model_version,
                )
            )
    missing_recipes = len(product_predictions) - len(recipes)
    if missing_recipes:
        warnings.append(
            f"{missing_recipes} forecast product(s) have no recipe, so their ingredient demand is not included."
        )
    run.products_forecast = len(product_predictions)
    run.warnings = warnings
    record_audit(
        db,
        action="forecast.generated",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="forecast_run",
        entity_id=run.id,
        details={"model": selected, "horizon_days": data.horizon_days},
        ip_address=ctx.ip,
    )
    realtime.emit(
        db,
        ctx.restaurant_id,
        "forecast.generated",
        entity_id=run.id,
        data={"model": selected},
        actor_user_id=ctx.user_id,
    )
    db.commit()
    return get_run(db, ctx, run.id)


# --------------------------------------------------------------------------- reading


def refresh_actuals(db: Session, ctx: RestaurantContext, run: ForecastRun) -> None:
    """Fill in actual quantities for forecast days that are now complete."""
    today = analytics.local_today(ctx)
    pending = db.scalars(
        select(Forecast).where(
            Forecast.run_id == run.id, Forecast.actual_quantity.is_(None), Forecast.forecast_date < today
        )
    ).all()
    if not pending:
        return
    start = min(f.forecast_date for f in pending)
    end = max(f.forecast_date for f in pending)
    timezone = ctx.restaurant.timezone
    sold = {(p, d): q for p, d, q in analytics.daily_product_quantities(db, ctx.restaurant_id, timezone, start, end)}
    trading = open_days(db, ctx.restaurant_id, timezone, start, end)
    lower, upper = analytics.utc_bounds_for(timezone, start, end)
    day = cast(func.timezone(timezone, InventoryMovement.created_at), Date)
    used = {
        (i, d): -q
        for i, d, q in db.execute(
            select(InventoryMovement.ingredient_id, day, func.sum(InventoryMovement.quantity))
            .where(
                InventoryMovement.restaurant_id == ctx.restaurant_id,
                InventoryMovement.movement_type.in_([MovementType.SALE, MovementType.SALE_REVERSAL]),
                InventoryMovement.created_at >= lower,
                InventoryMovement.created_at < upper,
            )
            .group_by(InventoryMovement.ingredient_id, day)
        ).all()
    }
    for f in pending:
        if f.forecast_date not in trading:
            continue  # Closed day: no actual to compare with.
        if f.target_type == ForecastTarget.PRODUCT:
            f.actual_quantity = Decimal(sold.get((f.product_id, f.forecast_date), 0))
        else:
            f.actual_quantity = Decimal(used.get((f.ingredient_id, f.forecast_date), 0))
    db.commit()


FORECAST_MAX_AGE_DAYS = 7


def is_forecast_stale(run_created_on: date, covers_until: date | None, today: date) -> bool:
    """A forecast is stale once it no longer predicts tomorrow, or it is over a week old."""
    return covers_until is None or covers_until <= today or (today - run_created_on).days > FORECAST_MAX_AGE_DAYS


def get_run(db: Session, ctx: RestaurantContext, run_id: uuid.UUID) -> ForecastRunOut:
    run = get_owned(db, ForecastRun, run_id, ctx.restaurant_id, "Forecast run")
    refresh_actuals(db, ctx, run)
    out = ForecastRunOut.model_validate(run)
    out.metrics = sorted(
        [MetricOut.model_validate(m) for m in run.metrics], key=lambda m: models.SELECTION_ORDER.index(m.model_name)
    )
    rows = db.scalars(select(Forecast).where(Forecast.run_id == run.id).order_by(Forecast.forecast_date)).all()
    out.covers_until = rows[-1].forecast_date if rows else None
    out.is_stale = is_forecast_stale(
        analytics.local_date_of(ctx, run.created_at), out.covers_until, analytics.local_today(ctx)
    )
    product_names = dict(
        db.execute(select(Product.id, Product.name).where(Product.restaurant_id == ctx.restaurant_id)).all()
    )
    ingredients = {i.id: i for i in db.scalars(scoped(Ingredient, ctx.restaurant_id)).all()}
    grouped: dict[tuple[str, uuid.UUID], list[Forecast]] = defaultdict(list)
    for f in rows:
        key = ("p", f.product_id) if f.target_type == ForecastTarget.PRODUCT else ("i", f.ingredient_id)
        grouped[key].append(f)  # type: ignore[arg-type]
    for (kind, target_id), points in grouped.items():
        pts = [
            ForecastPoint(
                date=p.forecast_date,
                horizon_day=p.horizon_day,
                predicted_quantity=p.predicted_quantity,
                actual_quantity=p.actual_quantity,
            )
            for p in points
        ]
        total = sum((p.predicted_quantity for p in points), Decimal(0))
        if kind == "p":
            out.products.append(
                ProductForecast(
                    product_id=target_id,
                    product_name=product_names.get(target_id, "?"),
                    model_name=points[0].model_name,
                    total_predicted=total,
                    points=pts,
                )
            )
        else:
            ingredient = ingredients.get(target_id)
            out.ingredients.append(
                IngredientForecast(
                    ingredient_id=target_id,
                    ingredient_name=ingredient.name if ingredient else "?",
                    base_unit=ingredient.base_unit.value if ingredient else "",
                    total_predicted=total,
                    points=pts,
                )
            )
    out.products.sort(key=lambda p: -p.total_predicted)
    out.ingredients.sort(key=lambda i: i.ingredient_name)
    return out


def list_runs(db: Session, ctx: RestaurantContext, limit: int = 20) -> list[ForecastRunSummary]:
    runs = db.scalars(scoped(ForecastRun, ctx.restaurant_id).order_by(ForecastRun.created_at.desc()).limit(limit)).all()
    return [ForecastRunSummary.model_validate(r) for r in runs]


def latest_run(db: Session, ctx: RestaurantContext) -> ForecastRun | None:
    return db.scalar(scoped(ForecastRun, ctx.restaurant_id).order_by(ForecastRun.created_at.desc()).limit(1))


def product_history(db: Session, ctx: RestaurantContext, product_id: uuid.UUID, days: int) -> ProductHistory:
    product = get_owned(db, Product, product_id, ctx.restaurant_id, "Product")
    today = analytics.local_today(ctx)
    start = today - timedelta(days=days)
    end = today - timedelta(days=1)
    timezone = ctx.restaurant.timezone
    sold = {
        d: q
        for p, d, q in analytics.daily_product_quantities(db, ctx.restaurant_id, timezone, start, end)
        if p == product.id
    }
    trading = open_days(db, ctx.restaurant_id, timezone, start, end)
    run = latest_run(db, ctx)
    # For past days use the most recent forecast that was made before the day (an honest "as predicted").
    past_predictions: dict[date, Decimal] = {}
    for f, created in db.execute(
        select(Forecast, ForecastRun.created_at)
        .join(ForecastRun, ForecastRun.id == Forecast.run_id)
        .where(Forecast.product_id == product.id, Forecast.forecast_date >= start)
        .order_by(ForecastRun.created_at)
    ).all():
        day_start, _ = analytics.utc_bounds_for(timezone, f.forecast_date, f.forecast_date)
        if created < day_start:
            past_predictions[f.forecast_date] = f.predicted_quantity
    points = []
    current = start
    while current <= end:
        is_open = current in trading
        points.append(
            HistoryPoint(
                date=current,
                actual_quantity=float(sold.get(current, 0)) if is_open else None,
                predicted_quantity=float(past_predictions[current]) if current in past_predictions else None,
                is_future=False,
                closed=not is_open,
            )
        )
        current += timedelta(days=1)
    if run is not None:
        future = db.scalars(
            select(Forecast)
            .where(Forecast.run_id == run.id, Forecast.product_id == product.id, Forecast.forecast_date >= today)
            .order_by(Forecast.forecast_date)
        ).all()
        points.extend(
            HistoryPoint(
                date=f.forecast_date,
                actual_quantity=None,
                predicted_quantity=float(f.predicted_quantity),
                is_future=True,
            )
            for f in future
        )
    return ProductHistory(
        product_id=product.id,
        product_name=product.name,
        run_id=run.id if run else None,
        model_name=run.model_name if run else None,
        points=points,
    )


def ingredient_demand(
    db: Session, run: ForecastRun, ingredient_id: uuid.UUID, start: date, days: int
) -> tuple[Decimal, int]:
    """Forecast demand for `days` days from `start`. Returns (demand, days covered by the forecast)."""
    rows = db.scalars(
        select(Forecast).where(
            Forecast.run_id == run.id,
            Forecast.ingredient_id == ingredient_id,
            Forecast.forecast_date >= start,
            Forecast.forecast_date < start + timedelta(days=days),
        )
    ).all()
    return sum((r.predicted_quantity for r in rows), Decimal(0)), len(rows)


def require_run(db: Session, ctx: RestaurantContext, run_id: uuid.UUID | None) -> ForecastRun:
    if run_id is not None:
        return get_owned(db, ForecastRun, run_id, ctx.restaurant_id, "Forecast run")
    run = latest_run(db, ctx)
    if run is None:
        raise NotFound("Generate a forecast before creating reorder recommendations.", code="no_forecast")
    return run
