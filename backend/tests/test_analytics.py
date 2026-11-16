"""Analytics, dashboard and CSV reports computed from persisted data."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import update

from app.models import Order
from tests.conftest import Factory


def _paid_order(client, cashier, method, items, *, discount=None, order_type="TAKEAWAY", table_id=None) -> dict:
    payload = {"order_type": order_type, "items": items, "confirm": True}
    if discount:
        payload["discount"] = discount
    if table_id:
        payload["table_id"] = table_id
    order = client.post("/api/v1/orders", json=payload, headers=cashier.headers)
    assert order.status_code == 201, order.text
    order = order.json()
    paid = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=cashier.headers,
        json={"payment_method_id": method, "amount_minor": order["total_minor"]},
    )
    assert paid.status_code == 201, paid.text
    return paid.json()


def _set_paid_at(db, order_id: str, when: datetime) -> None:
    db.execute(update(Order).where(Order.id == uuid.UUID(order_id)).values(paid_at=when))
    db.commit()


def test_summary_metrics_and_timezone_buckets(client: TestClient, factory: Factory, db) -> None:
    rid = factory.restaurant("Analytics Thai", prices_include_tax=False, tax_rate_bps=700, timezone="Asia/Bangkok")
    manager, cashier = factory.manager(rid), factory.cashier(rid)
    noodles = factory.category(manager, "Noodles")
    drinks = factory.category(manager, "Drinks")
    pad_thai = factory.product(manager, noodles["id"], "Pad Thai", 10000)
    tea = factory.product(manager, drinks["id"], "Iced tea", 5000)
    factory.product(manager, drinks["id"], "Coconut juice", 6000)  # never sold -> slow product
    cash = factory.payment_method_id(manager, "CASH")
    card = factory.payment_method_id(manager, "CARD")

    late = _paid_order(client, cashier, cash, [{"product_id": pad_thai["id"], "quantity": 2}])  # 214.00
    early = _paid_order(
        client,
        manager,
        card,
        [{"product_id": tea["id"], "quantity": 1}],
        discount={"kind": "FIXED", "value": 1000, "reason": "promo"},
    )  # (50-10)*1.07 = 42.80
    # 23:30 Bangkok on 20 Oct and 00:30 Bangkok on 21 Oct (both 20 Oct in UTC).
    _set_paid_at(db, late["id"], datetime(2026, 10, 20, 16, 30, tzinfo=UTC))
    _set_paid_at(db, early["id"], datetime(2026, 10, 20, 17, 30, tzinfo=UTC))
    # Cancelled and unpaid orders never count.
    unpaid = client.post(
        "/api/v1/orders",
        headers=cashier.headers,
        json={"order_type": "TAKEAWAY", "items": [{"product_id": tea["id"], "quantity": 5}], "confirm": True},
    ).json()
    client.post(f"/api/v1/orders/{unpaid['id']}/cancel", headers=manager.headers, json={"reason": "test"})

    h = manager.headers
    days = client.get(
        "/api/v1/analytics/sales-by-day", headers=h, params={"start_date": "2026-10-20", "end_date": "2026-10-21"}
    ).json()
    assert [(d["date"], d["order_count"]) for d in days] == [("2026-10-20", 1), ("2026-10-21", 1)]
    hours = client.get(
        "/api/v1/analytics/sales-by-hour", headers=h, params={"start_date": "2026-10-20", "end_date": "2026-10-21"}
    ).json()
    assert hours[23]["order_count"] == 1 and hours[0]["order_count"] == 1 and len(hours) == 24

    summary = client.get(
        "/api/v1/analytics/summary", headers=h, params={"start_date": "2026-10-20", "end_date": "2026-10-21"}
    ).json()
    assert summary["order_count"] == 2
    assert summary["gross_sales_minor"] == 20000 + 5000
    assert summary["discounts_minor"] == 1000
    assert summary["tax_minor"] == 1400 + 280
    assert summary["total_billed_minor"] == 21400 + 4280
    assert summary["net_sales_minor"] == 24000
    assert summary["average_order_value_minor"] == (21400 + 4280) // 2
    assert summary["items_sold"] == 3

    only_21 = client.get(
        "/api/v1/analytics/summary", headers=h, params={"start_date": "2026-10-21", "end_date": "2026-10-21"}
    ).json()
    assert only_21["order_count"] == 1 and only_21["total_billed_minor"] == 4280

    by_card = client.get(
        "/api/v1/analytics/summary",
        headers=h,
        params={"start_date": "2026-10-20", "end_date": "2026-10-21", "payment_method": "CARD"},
    ).json()
    assert by_card["order_count"] == 1
    by_category = client.get(
        "/api/v1/analytics/sales-by-category", headers=h, params={"start_date": "2026-10-20", "end_date": "2026-10-21"}
    ).json()
    assert [(c["category_name"], c["sales_minor"]) for c in by_category] == [("Noodles", 20000), ("Drinks", 5000)]
    top = client.get(
        "/api/v1/analytics/top-products", headers=h, params={"start_date": "2026-10-20", "end_date": "2026-10-21"}
    ).json()
    assert top[0]["product_name"] == "Pad Thai" and top[0]["quantity"] == 2
    slow = client.get(
        "/api/v1/analytics/slow-products", headers=h, params={"start_date": "2026-10-20", "end_date": "2026-10-21"}
    ).json()
    assert slow[0]["product_name"] == "Coconut juice" and slow[0]["quantity"] == 0
    payments = client.get("/api/v1/analytics/payment-distribution", headers=h).json()
    assert {p["method_code"] for p in payments} == {"CASH", "CARD"}
    assert all(p["is_simulated"] for p in payments)

    comparison = client.get(
        "/api/v1/analytics/comparison", headers=h, params={"start_date": "2026-10-21", "end_date": "2026-10-21"}
    ).json()
    assert comparison["previous"]["order_count"] == 1 and comparison["current"]["order_count"] == 1
    assert comparison["previous"]["range"]["start_date"] == "2026-10-20"

    bad = client.get(
        "/api/v1/analytics/summary", headers=h, params={"start_date": "2026-10-21", "end_date": "2026-10-01"}
    )
    assert bad.status_code == 422


def test_refunds_reduce_net_sales_and_profit_estimate(client: TestClient, factory: Factory) -> None:
    rid = factory.restaurant("Profit Thai", prices_include_tax=True, tax_rate_bps=700)
    manager = factory.manager(rid)
    egg = factory.ingredient(manager, "Egg", "piece", stock=20, opening_unit_cost_minor="500")
    category = factory.category(manager)
    omelette = factory.product(manager, category["id"], "Omelette", 10700)
    factory.recipe(manager, omelette["id"], [{"ingredient_id": egg["id"], "quantity": "2"}])
    cash = factory.payment_method_id(manager)
    order = _paid_order(client, manager, cash, [{"product_id": omelette["id"], "quantity": 1}])
    client.post(
        f"/api/v1/orders/{order['id']}/refunds",
        headers=manager.headers,
        json={"payment_id": order["payments"][0]["id"], "amount_minor": 5350, "reason": "half"},
    )
    client.post(
        "/api/v1/inventory/movements",
        headers=manager.headers,
        json={"ingredient_id": egg["id"], "movement_type": "WASTE", "quantity": "3", "reason": "dropped"},
    )
    summary = client.get("/api/v1/analytics/summary", headers=manager.headers).json()
    assert summary["refunds_minor"] == 5350
    assert summary["net_sales_minor"] == 10700 - 5350
    # The daily series uses the same definition, so the dashboard trend matches the headline figure.
    days = client.get(
        "/api/v1/analytics/sales-by-day",
        headers=manager.headers,
        params={"start_date": summary["range"]["start_date"], "end_date": summary["range"]["end_date"]},
    ).json()
    assert sum(d["net_sales_minor"] for d in days) == summary["net_sales_minor"]
    assert summary["total_collected_minor"] == 5350
    assert summary["estimated_ingredient_cost_minor"] == 1000
    # Revenue ex VAT: 10000 - 5000 refunded (ex VAT) - 1000 ingredient cost.
    assert summary["estimated_gross_profit_minor"] == 4000
    assert summary["cost_data_complete"] is True
    waste = client.get("/api/v1/analytics/waste", headers=manager.headers).json()
    assert waste[0]["quantity"] == 3.0 and waste[0]["estimated_cost_minor"] == 1500
    consumption = client.get("/api/v1/analytics/ingredient-consumption", headers=manager.headers).json()
    assert consumption[0]["quantity"] == 2.0


def test_dashboard_is_role_aware(client: TestClient, factory: Factory) -> None:
    rid = factory.restaurant()
    manager, cashier, kitchen = factory.manager(rid), factory.cashier(rid), factory.kitchen(rid)
    factory.ingredient(manager, "Basil", "g", stock=10, reorder_level="100")
    category = factory.category(manager)
    product = factory.product(manager, category["id"], "Basil chicken", 9000)
    _paid_order(client, cashier, factory.payment_method_id(manager), [{"product_id": product["id"], "quantity": 1}])
    full = client.get("/api/v1/analytics/dashboard", headers=manager.headers).json()
    assert full["today"]["order_count"] == 1
    assert [i["name"] for i in full["low_stock"]] == ["Basil"]
    assert len(full["sales_last_14_days"]) == 14
    assert full["insights"]
    limited = client.get("/api/v1/analytics/dashboard", headers=cashier.headers).json()
    assert limited["today"] is None and limited["low_stock"] == [] and limited["recent_orders"]
    assert client.get("/api/v1/analytics/dashboard", headers=kitchen.headers).status_code == 403
    assert client.get("/api/v1/analytics/summary", headers=cashier.headers).status_code == 403
    assert client.get("/api/v1/reports/orders.csv", headers=cashier.headers).status_code == 403


def test_csv_reports_escape_formulas(client: TestClient, factory: Factory) -> None:
    rid = factory.restaurant()
    manager = factory.manager(rid)
    category = factory.category(manager, "อาหารไทย")
    product = factory.product(manager, category["id"], '=HYPERLINK("http://evil")', 5000)
    _paid_order(client, manager, factory.payment_method_id(manager), [{"product_id": product["id"], "quantity": 1}])
    r = client.get("/api/v1/reports/product-sales.csv", headers=manager.headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    text = r.content.decode("utf-8-sig")
    assert "'=HYPERLINK" in text and "อาหารไทย" in text
    for path in ("daily-sales", "orders", "inventory-movements", "inventory-valuation", "purchases"):
        assert client.get(f"/api/v1/reports/{path}.csv", headers=manager.headers).status_code == 200


def test_payment_refunds_respect_order_filters(client: TestClient, factory: Factory) -> None:
    rid = factory.restaurant("Refund Filters", prices_include_tax=True, service_charge_bps=0)
    manager, cashier = factory.manager(rid), factory.cashier(rid)
    mains = factory.category(manager, "Mains")
    dish = factory.product(manager, mains["id"], "Dish", 10000)
    cash = factory.payment_method_id(manager, "CASH")
    table = factory.table(manager, "T9")
    dine_in = _paid_order(
        client, cashier, cash, [{"product_id": dish["id"], "quantity": 1}], order_type="DINE_IN", table_id=table["id"]
    )
    _paid_order(client, cashier, cash, [{"product_id": dish["id"], "quantity": 1}], order_type="TAKEAWAY")
    refund = client.post(
        f"/api/v1/orders/{dine_in['id']}/refunds",
        headers=manager.headers,
        json={"payment_id": dine_in["payments"][0]["id"], "amount_minor": 2500, "reason": "cold food"},
    )
    assert refund.status_code == 201, refund.text

    def cash_row(**params: str) -> dict:
        rows = client.get("/api/v1/analytics/payment-distribution", headers=manager.headers, params=params).json()
        return next(r for r in rows if r["method_code"] == "CASH")

    assert cash_row()["refunded_minor"] == 2500
    assert cash_row(order_type="DINE_IN")["refunded_minor"] == 2500
    # The refund belongs to a dine-in order, so it must not leak into the takeaway view.
    takeaway = cash_row(order_type="TAKEAWAY")
    assert takeaway["payment_count"] == 1 and takeaway["refunded_minor"] == 0


def test_consumption_is_valued_at_the_cost_in_effect_when_used(client: TestClient, factory: Factory) -> None:
    rid = factory.restaurant("Cost Basis")
    manager, cashier = factory.manager(rid), factory.cashier(rid)
    mains = factory.category(manager, "Mains")
    dish = factory.product(manager, mains["id"], "Rice bowl", 6000)
    rice = factory.ingredient(manager, "Rice", "g", 1000, opening_unit_cost_minor="4")  # ฿0.04/g
    factory.recipe(manager, dish["id"], [{"ingredient_id": rice["id"], "quantity": "200", "unit": "g"}])
    cash = factory.payment_method_id(manager, "CASH")
    _paid_order(client, cashier, cash, [{"product_id": dish["id"], "quantity": 2}])  # 400 g at 4 satang

    def rice_usage() -> dict:
        rows = client.get("/api/v1/analytics/ingredient-consumption", headers=manager.headers).json()
        return next(r for r in rows if r["ingredient_id"] == rice["id"])

    assert rice_usage()["quantity"] == 400 and rice_usage()["estimated_cost_minor"] == 1600
    # A later, much dearer delivery moves the average cost but must not revalue past sales.
    receipt = client.post(
        "/api/v1/inventory/movements",
        headers=manager.headers,
        json={
            "ingredient_id": rice["id"],
            "movement_type": "RECEIPT",
            "quantity": "600",
            "unit_cost_minor": "100",
            "reason": "Market",
        },
    )
    assert receipt.status_code == 201, receipt.text
    assert rice_usage()["estimated_cost_minor"] == 1600
    movements = client.get(
        "/api/v1/inventory/movements", headers=manager.headers, params={"ingredient_id": rice["id"]}
    ).json()["items"]
    sale = next(m for m in movements if m["movement_type"] == "SALE")
    assert sale["unit_cost_minor"] == 4


def test_day_in_progress_is_compared_with_the_same_hours_yesterday(
    client: TestClient, factory: Factory, db, monkeypatch
) -> None:
    from zoneinfo import ZoneInfo

    from app.services import analytics

    bangkok = ZoneInfo("Asia/Bangkok")
    monkeypatch.setattr(analytics, "local_now", lambda ctx: datetime(2026, 10, 21, 12, 0, tzinfo=bangkok))
    rid = factory.restaurant("Same Time", timezone="Asia/Bangkok")
    manager, cashier = factory.manager(rid), factory.cashier(rid)
    mains = factory.category(manager, "Mains")
    dish = factory.product(manager, mains["id"], "Dish", 10000)
    cash = factory.payment_method_id(manager, "CASH")
    paid = [_paid_order(client, cashier, cash, [{"product_id": dish["id"], "quantity": 1}]) for _ in range(3)]
    _set_paid_at(db, paid[0]["id"], datetime(2026, 10, 21, 9, 0, tzinfo=bangkok))  # today, before noon
    _set_paid_at(db, paid[1]["id"], datetime(2026, 10, 20, 10, 0, tzinfo=bangkok))  # yesterday morning
    _set_paid_at(db, paid[2]["id"], datetime(2026, 10, 20, 18, 0, tzinfo=bangkok))  # yesterday evening

    today = {"start_date": "2026-10-21", "end_date": "2026-10-21"}
    cmp = client.get("/api/v1/analytics/comparison", headers=manager.headers, params=today).json()
    assert cmp["current"]["order_count"] == 1
    # Only yesterday's sales up to 12:00 count, so the half day is not compared with a full day.
    assert cmp["previous"]["order_count"] == 1 and cmp["order_count_change_pct"] == 0
    assert cmp["previous"]["range"]["cutoff_time"] == "12:01:00"
    # A finished day is compared in full.
    past = {"start_date": "2026-10-20", "end_date": "2026-10-20"}
    full = client.get("/api/v1/analytics/comparison", headers=manager.headers, params=past).json()
    assert full["current"]["order_count"] == 2 and full["current"]["range"]["cutoff_time"] is None
    dashboard = client.get("/api/v1/analytics/dashboard", headers=manager.headers).json()
    assert dashboard["comparison"]["previous"]["order_count"] == 1
