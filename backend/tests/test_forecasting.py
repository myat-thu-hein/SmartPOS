"""Forecast metrics, models, backtesting, forecast runs and reorder recommendations."""

from __future__ import annotations

import math
import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.forecasting import models
from app.forecasting.evaluation import Series, backtest
from app.forecasting.metrics import evaluate, mae, mape, rmse
from app.models import Order, OrderItem, Restaurant
from app.models.enums import OrderStatus, OrderType, PaymentStatus
from app.services.recommendations import calculate, round_up_to_multiple
from tests.conftest import Factory

# --------------------------------------------------------------------------- metrics


def test_metrics_basic() -> None:
    actual, predicted = [10, 20, 30], [12, 18, 33]
    assert mae(actual, predicted) == pytest.approx(7 / 3)
    assert rmse(actual, predicted) == pytest.approx(math.sqrt((4 + 4 + 9) / 3))
    value, used, zeros = mape(actual, predicted)
    assert value == pytest.approx((0.2 + 0.1 + 0.1) / 3 * 100) and used == 3 and zeros == 0


def test_mape_handles_zero_actuals() -> None:
    value, used, zeros = mape([0, 10, 0], [2, 5, 1])
    assert value == pytest.approx(50.0) and used == 1 and zeros == 2
    result = evaluate([0, 0], [1, 2])
    assert result.mape is None and result.mae == 1.5
    assert "undefined" in (result.note or "")
    empty = evaluate([], [])
    assert empty.mae is None and empty.points == 0
    with pytest.raises(ValueError):
        mae([1], [1, 2])
    with pytest.raises(ValueError):
        mae([float("nan")], [1])


# --------------------------------------------------------------------------- models


def _weekly(weeks: int, start: date = date(2026, 1, 5)) -> np.ndarray:
    # Monday-based pattern: quiet early week, busy weekend.
    pattern = [5, 6, 7, 8, 12, 20, 18]
    return np.array([pattern[(start + timedelta(days=i)).weekday()] for i in range(weeks * 7)], dtype=float)


def test_baseline_models() -> None:
    start = date(2026, 1, 5)  # Monday
    values = _weekly(4, start)
    ma = models.create("moving_average").fit(start, values)
    assert ma.predict([1])[0] == pytest.approx(values[-7:].mean())
    naive = models.create("seasonal_naive").fit(start, values)
    # Next day after a Sunday is a Monday -> 5.
    assert naive.predict([1, 6])[0] == 5 and naive.predict([1, 6])[1] == 20
    dow = models.create("dow_average").fit(start, values)
    assert list(dow.predict([1, 2, 3, 4, 5, 6, 7])) == [5, 6, 7, 8, 12, 20, 18]
    with pytest.raises(ValueError):
        models.create("dow_average").fit(start, values[:10])


def test_closed_days_are_not_zero_demand() -> None:
    start = date(2026, 1, 5)
    values = _weekly(3, start)
    values[-7] = np.nan  # last Monday closed
    naive = models.create("seasonal_naive").fit(start, values)
    assert naive.predict([1])[0] == 5  # falls back to the Monday before
    assert models.create("moving_average").fit(start, values).predict([1])[0] > 0


def test_ridge_learns_weekly_pattern_and_never_negative() -> None:
    start = date(2026, 1, 5)
    values = _weekly(10, start)
    model = models.create("ridge_lags").fit(start, values)
    preds = model.predict([1, 2, 3, 4, 5, 6, 7])
    assert np.all(preds >= 0)
    assert preds[5] > preds[0]  # Saturday busier than Monday
    assert np.abs(preds - np.array([5, 6, 7, 8, 12, 20, 18])).mean() < 2


def test_backtest_uses_only_past_data() -> None:
    """A model that peeks at the future would score perfectly on this series."""
    start = date(2026, 1, 5)
    rng = np.random.default_rng(0)
    values = rng.integers(0, 50, size=60).astype(float)
    seen_lengths: list[int] = []

    class Spy(models.MovingAverage):
        name = "spy"

        def _fit(self) -> None:
            seen_lengths.append(len(self.values))

    models.MODEL_CLASSES["spy"] = Spy
    try:
        result = backtest("spy", [Series("x", start, values)], horizon=3, eval_origins=10)
    finally:
        del models.MODEL_CLASSES["spy"]
    assert result.points > 0
    assert max(seen_lengths) <= len(values) - 1, "the final observation must never be in a training window"
    assert seen_lengths == sorted(seen_lengths)


def test_seasonal_models_beat_moving_average_on_seasonal_data() -> None:
    start = date(2026, 1, 5)
    series = [Series("a", start, _weekly(10, start))]
    ma = backtest("moving_average", series, horizon=7)
    dow = backtest("dow_average", series, horizon=7)
    assert dow.mae is not None and ma.mae is not None and dow.mae < ma.mae


# --------------------------------------------------------------------------- recommendations formula


def test_reorder_formula_and_rounding() -> None:
    raw, suggested = calculate(Decimal(800), Decimal(1200), Decimal(500), Decimal(0), Decimal(1000))
    assert raw == Decimal(900) and suggested == Decimal(1000)
    raw, suggested = calculate(Decimal(5000), Decimal(1200), Decimal(500), Decimal(0), None)
    assert raw == Decimal(-3300) and suggested == 0
    _, with_incoming = calculate(Decimal(100), Decimal(1000), Decimal(0), Decimal(600), None)
    assert with_incoming == Decimal(300)
    assert round_up_to_multiple(Decimal("2001"), Decimal(1000)) == Decimal(3000)
    assert round_up_to_multiple(Decimal("0"), Decimal(1000)) == 0


# --------------------------------------------------------------------------- forecast runs (API)


def _seed_history(db, restaurant_id: uuid.UUID, product: dict, days: int, closed_weekday: int | None = None) -> None:
    """Create paid orders for the past `days` days with a weekly pattern (test data)."""
    restaurant = db.get(Restaurant, restaurant_id)
    tz = ZoneInfo(restaurant.timezone)
    today = datetime.now(tz).date()
    pattern = [4, 5, 6, 7, 10, 14, 12]
    number = 1000
    for back in range(days, 0, -1):
        day = today - timedelta(days=back)
        if closed_weekday is not None and day.weekday() == closed_weekday:
            continue
        qty = pattern[day.weekday()]
        number += 1
        paid_at = datetime.combine(day, time(12, 0), tzinfo=tz).astimezone(UTC)
        order = Order(
            restaurant_id=restaurant_id,
            order_number=number,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.COMPLETED,
            payment_status=PaymentStatus.PAID,
            subtotal_minor=qty * 1000,
            total_minor=qty * 1000,
            amount_paid_minor=qty * 1000,
            paid_at=paid_at,
            created_at=paid_at,
            confirmed_at=paid_at,
            stock_committed=True,
        )
        order.items.append(
            OrderItem(
                restaurant_id=restaurant_id,
                product_id=uuid.UUID(product["id"]),
                product_name=product["name"],
                base_price_minor=1000,
                unit_price_minor=1000,
                quantity=qty,
                line_total_minor=qty * 1000,
            )
        )
        db.add(order)
    db.commit()


def test_forecast_requires_history(client: TestClient, factory: Factory) -> None:
    rid = factory.restaurant()
    manager = factory.manager(rid)
    r = client.post("/api/v1/forecast/runs", headers=manager.headers, json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "insufficient_data"
    assert client.get("/api/v1/forecast/latest", headers=manager.headers).status_code == 404


def test_forecast_run_selects_model_by_backtest_and_stores_results(client: TestClient, factory: Factory, db) -> None:
    rid = factory.restaurant("Forecast Thai")
    manager = factory.manager(rid)
    basil = factory.ingredient(manager, "Thai basil", "g", stock=500, safety_stock="200")
    category = factory.category(manager)
    product = factory.product(manager, category["id"], "Basil chicken", 9000)
    factory.recipe(manager, product["id"], [{"ingredient_id": basil["id"], "quantity": "20", "waste_factor": "0.05"}])
    _seed_history(db, rid, product, days=70, closed_weekday=0)  # closed on Mondays

    r = client.post("/api/v1/forecast/runs", headers=manager.headers, json={"horizon_days": 7})
    assert r.status_code == 201, r.text
    run = r.json()
    metrics = {m["model_name"]: m for m in run["metrics"]}
    assert set(metrics) == {"moving_average", "seasonal_naive", "dow_average", "ridge_lags"}
    selected = [m for m in run["metrics"] if m["is_selected"]]
    assert len(selected) == 1 and selected[0]["model_name"] == run["model_name"]
    best_mae = min(m["mae"] for m in run["metrics"] if m["mae"] is not None)
    assert selected[0]["mae"] == best_mae
    assert metrics["dow_average"]["mae"] < metrics["moving_average"]["mae"]
    assert run["history_days"] < 70  # Mondays were excluded as closed days, not counted as zero
    product_fc = run["products"][0]
    assert len(product_fc["points"]) == 7
    bangkok_tomorrow = datetime.now(ZoneInfo("Asia/Bangkok")).date() + timedelta(days=1)
    assert product_fc["points"][0]["date"] == bangkok_tomorrow.isoformat()
    # A fresh run covers the next 7 days and is not stale.
    assert run["covers_until"] == (bangkok_tomorrow + timedelta(days=6)).isoformat() and run["is_stale"] is False
    # Ingredient demand = product forecast x 20 g x 1.05.
    ingredient_fc = run["ingredients"][0]
    assert ingredient_fc["ingredient_name"] == "Thai basil"
    for p_point, i_point in zip(product_fc["points"], ingredient_fc["points"], strict=True):
        assert i_point["predicted_quantity"] == pytest.approx(p_point["predicted_quantity"] * 21, rel=1e-3)

    history = client.get(
        f"/api/v1/forecast/products/{product['id']}/history", headers=manager.headers, params={"days": 28}
    ).json()
    past = [p for p in history["points"] if not p["is_future"]]
    future = [p for p in history["points"] if p["is_future"]]
    assert len(future) == 7 and any(p["closed"] for p in past)
    assert all(p["actual_quantity"] is None for p in past if p["closed"])

    manual = client.post(
        "/api/v1/forecast/runs", headers=manager.headers, json={"horizon_days": 3, "model": "moving_average"}
    )
    assert manual.json()["model_name"] == "moving_average" and manual.json()["selection_strategy"] == "manual"
    bad = client.post("/api/v1/forecast/runs", headers=manager.headers, json={"model": "magic"})
    assert bad.status_code == 422
    assert len(client.get("/api/v1/forecast/runs", headers=manager.headers).json()) == 2


def test_short_history_warns(client: TestClient, factory: Factory, db) -> None:
    rid = factory.restaurant()
    manager = factory.manager(rid)
    category = factory.category(manager)
    product = factory.product(manager, category["id"], "Som tam", 6000)
    _seed_history(db, rid, product, days=5)
    run = client.post("/api/v1/forecast/runs", headers=manager.headers, json={"horizon_days": 2}).json()
    assert any("unreliable" in w for w in run["warnings"])
    assert run["model_name"] in {"moving_average", "seasonal_naive"}


def test_recommendation_flow(client: TestClient, factory: Factory, db) -> None:
    rid = factory.restaurant("Reorder Thai")
    manager, cashier = factory.manager(rid), factory.cashier(rid)
    basil = factory.ingredient(manager, "Thai basil", "g", stock=300, safety_stock="200", reorder_level="250")
    chili = factory.ingredient(manager, "Chili", "g", stock=100000)
    category = factory.category(manager)
    product = factory.product(manager, category["id"], "Basil chicken", 9000)
    factory.recipe(
        manager,
        product["id"],
        [{"ingredient_id": basil["id"], "quantity": "20"}, {"ingredient_id": chili["id"], "quantity": "5"}],
    )
    supplier = client.post(
        "/api/v1/suppliers", headers=manager.headers, json={"name": "Herb Farm", "lead_time_days": 2}
    ).json()
    client.post(
        f"/api/v1/suppliers/{supplier['id']}/ingredients",
        headers=manager.headers,
        json={"ingredient_id": basil["id"], "min_order_quantity": "500", "unit_cost_minor": "10"},
    )
    _seed_history(db, rid, product, days=42)

    no_run = client.post("/api/v1/recommendations/generate", headers=manager.headers, json={})
    assert no_run.status_code == 404
    client.post("/api/v1/forecast/runs", headers=manager.headers, json={"horizon_days": 7})
    assert client.post("/api/v1/recommendations/generate", headers=cashier.headers, json={}).status_code == 403
    gen = client.post("/api/v1/recommendations/generate", headers=manager.headers, json={"review_period_days": 3})
    assert gen.status_code == 200, gen.text
    result = gen.json()
    names = [r["ingredient_name"] for r in result["created"]]
    assert names == ["Thai basil"], "chili has plenty of stock"
    rec = result["created"][0]
    assert rec["coverage_days"] == 5 and rec["lead_time_days"] == 2
    expected_raw = rec["forecast_demand"] + 200 - 300 - 0
    assert rec["raw_quantity"] == pytest.approx(expected_raw, abs=0.01)
    assert rec["suggested_quantity"] % 500 == 0 and rec["suggested_quantity"] >= rec["raw_quantity"]
    assert "safety stock" in rec["reason"] and rec["calculation"]["formula"]
    assert rec["status"] == "PENDING" and rec["supplier_name"] == "Herb Farm"

    regen = client.post("/api/v1/recommendations/generate", headers=manager.headers, json={}).json()
    assert regen["superseded"] == 1
    pending = client.get("/api/v1/recommendations", params={"status": "PENDING"}, headers=manager.headers).json()
    assert len(pending) == 1
    rec_id = pending[0]["id"]

    not_approved = client.post(
        "/api/v1/recommendations/purchase-orders", headers=manager.headers, json={"recommendation_ids": [rec_id]}
    )
    assert not_approved.status_code == 409
    modified = client.post(
        f"/api/v1/recommendations/{rec_id}/modify",
        headers=manager.headers,
        json={"quantity": "1.5", "unit": "kg", "note": "weekend event"},
    )
    assert modified.json()["status"] == "MODIFIED" and modified.json()["approved_quantity"] == 1500.0
    assert modified.json()["reviewer_name"]
    again = client.post(f"/api/v1/recommendations/{rec_id}/approve", headers=manager.headers, json={})
    assert again.status_code == 409
    pos = client.post(
        "/api/v1/recommendations/purchase-orders", headers=manager.headers, json={"recommendation_ids": [rec_id]}
    )
    assert pos.status_code == 200, pos.text
    po = client.get(f"/api/v1/purchase-orders/{pos.json()[0]['purchase_order_id']}", headers=manager.headers).json()
    assert po["status"] == "DRAFT", "purchase orders are never submitted automatically"
    assert po["items"][0]["quantity_ordered"] == 1500.0
    done = client.get("/api/v1/recommendations", params={"status": "COMPLETED"}, headers=manager.headers).json()
    assert done[0]["purchase_order_id"] == po["id"]


def test_ridge_closed_form_recovers_coefficients_and_shrinks() -> None:
    from app.forecasting.models import RidgeFit

    rng = np.random.default_rng(7)
    x = rng.normal(size=(200, 3))
    y = x @ np.array([2.0, -1.0, 0.5]) + 10.0
    exact = RidgeFit.fit(x, y, alpha=1e-9)
    assert np.allclose(exact.coef, [2.0, -1.0, 0.5], atol=1e-6) and abs(exact.intercept - 10.0) < 1e-6
    shrunk = RidgeFit.fit(x, y, alpha=1e4)
    assert np.linalg.norm(shrunk.coef) < 0.1 * np.linalg.norm(exact.coef)  # the penalty shrinks weights
    assert abs(shrunk.intercept - y.mean()) < 1.0  # the intercept is not penalised
