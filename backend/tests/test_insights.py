"""Stock-out risk, dashboard insights and POS suggestions, computed from real records."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import text, update

from app.forecasting.service import is_forecast_stale
from app.models import InventoryMovement, Order
from tests.conftest import Factory

BANGKOK = ZoneInfo("Asia/Bangkok")


def _sell(client: TestClient, cashier, items: list[tuple[dict, int]], customer_id: str | None = None) -> dict:
    payload = {
        "order_type": "TAKEAWAY",
        "items": [{"product_id": p["id"], "quantity": q} for p, q in items],
        "confirm": True,
    }
    if customer_id:
        payload["customer_id"] = customer_id
    order = client.post("/api/v1/orders", headers=cashier.headers, json=payload)
    assert order.status_code == 201, order.text
    order = order.json()
    methods = client.get("/api/v1/payments/methods", headers=cashier.headers).json()
    cash = next(m["id"] for m in methods if m["code"] == "CASH")
    paid = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=cashier.headers,
        json={"payment_method_id": cash, "amount_minor": order["total_minor"]},
    )
    assert paid.status_code == 201, paid.text
    return paid.json()


def _move_to_yesterday(db, restaurant_id: uuid.UUID) -> None:
    """Shift today's sales and their stock movements to yesterday (local time), keeping the hour.

    The movement ledger is append-only, so this test-only time travel disables its trigger
    for the duration of the update (inside one transaction of the throwaway test database).
    """
    yesterday = datetime.now(BANGKOK) - timedelta(days=1)
    db.execute(update(Order).where(Order.restaurant_id == restaurant_id).values(paid_at=yesterday))
    db.execute(text("ALTER TABLE inventory_movements DISABLE TRIGGER trg_inventory_movements_append_only"))
    db.execute(
        update(InventoryMovement)
        .where(InventoryMovement.restaurant_id == restaurant_id, InventoryMovement.movement_type == "SALE")
        .values(created_at=yesterday)
    )
    db.execute(text("ALTER TABLE inventory_movements ENABLE TRIGGER trg_inventory_movements_append_only"))
    db.commit()


def test_stock_risk_compares_days_of_cover_with_lead_time(client: TestClient, factory: Factory, db) -> None:
    rid = factory.restaurant("Risk Thai", timezone="Asia/Bangkok")
    manager, cashier = factory.manager(rid), factory.cashier(rid)
    supplier = client.post(
        "/api/v1/suppliers", headers=manager.headers, json={"name": "Rice Co", "lead_time_days": 5}
    ).json()
    rice = factory.ingredient(manager, "Rice", "g", stock=1000, default_supplier_id=supplier["id"])
    # The price-list lead time (3 days) overrides the supplier's general lead time (5 days).
    link = client.post(
        f"/api/v1/suppliers/{supplier['id']}/ingredients",
        headers=manager.headers,
        json={"ingredient_id": rice["id"], "lead_time_days": 3},
    )
    assert link.status_code == 201, link.text
    salt = factory.ingredient(manager, "Salt", "g", stock=100, reorder_level="200")
    factory.ingredient(manager, "Pepper", "g", stock=500)
    factory.ingredient(manager, "Mint", "g", stock=0)
    dish = factory.product(manager, factory.category(manager)["id"], "Rice bowl", 6000)
    factory.recipe(manager, dish["id"], [{"ingredient_id": rice["id"], "quantity": "200", "unit": "g"}])

    _sell(client, cashier, [(dish, 2)])  # 400 g used; 600 g left
    _move_to_yesterday(db, rid)

    r = client.get("/api/v1/inventory/stock-risk", headers=manager.headers)
    assert r.status_code == 200, r.text
    risks = {x["ingredient_name"]: x for x in r.json()}
    assert [x["ingredient_name"] for x in r.json()] == ["Mint", "Rice", "Salt", "Pepper"]  # most urgent first

    rice_risk = risks["Rice"]
    assert rice_risk["level"] == "critical"  # 1.5 days of cover, 3 days to deliver
    assert rice_risk["usage_basis"] == "recent_sales" and float(rice_risk["daily_usage"]) == 400
    assert rice_risk["days_of_cover"] == 1.5 and rice_risk["lead_time_days"] == 3
    assert rice_risk["supplier_name"] == "Rice Co"
    assert rice_risk["runs_out_on"] == (datetime.now(BANGKOK).date() + timedelta(days=1)).isoformat()
    assert "1.5 day(s) left at 400 g/day (last 14 days); lead time is 3 day(s)." in rice_risk["reason"]

    assert risks["Mint"]["level"] == "out"
    assert risks["Salt"]["level"] == "warning" and "reorder level (200 g)" in risks["Salt"]["reason"]
    assert risks["Pepper"]["level"] == "ok" and risks["Pepper"]["reason"] == "No recent use."
    assert salt["id"] == risks["Salt"]["ingredient_id"]

    dash = client.get("/api/v1/analytics/dashboard", headers=manager.headers).json()
    stock = next(i for i in dash["insights"] if i["key"] == "stock-risk")
    assert stock["severity"] == "critical" and stock["link"] == "/inventory"
    assert "Out of stock: Mint." in stock["detail"] and "Rice lasts about 1.5 day(s)" in stock["detail"]
    assert dash["insights"][0]["key"] == "stock-risk"  # urgent insights come first
    assert [x["ingredient_name"] for x in dash["stock_at_risk"]] == ["Mint", "Rice", "Salt"]
    assert dash["stock_at_risk_count"] == 3 and dash["stock_critical_count"] == 2

    # Once stock is on order, the risk is downgraded and the incoming quantity is stated.
    po = client.post(
        "/api/v1/purchase-orders",
        headers=manager.headers,
        json={"supplier_id": supplier["id"], "items": [{"ingredient_id": rice["id"], "quantity": "2", "unit": "kg"}]},
    ).json()
    client.post(f"/api/v1/purchase-orders/{po['id']}/submit", headers=manager.headers)
    rice_risk = next(
        x
        for x in client.get("/api/v1/inventory/stock-risk", headers=manager.headers).json()
        if x["ingredient_name"] == "Rice"
    )
    assert rice_risk["level"] == "warning" and float(rice_risk["incoming"]) == 2000
    assert rice_risk["reason"].endswith("2 kg on order.")

    assert client.get("/api/v1/inventory/stock-risk", headers=cashier.headers).status_code == 403


def test_forecast_staleness_rule() -> None:
    today = date(2026, 11, 12)
    assert not is_forecast_stale(today, today + timedelta(days=7), today)
    assert is_forecast_stale(today - timedelta(days=3), today, today)  # no longer predicts tomorrow
    assert is_forecast_stale(today - timedelta(days=8), today + timedelta(days=30), today)  # over a week old
    assert is_forecast_stale(today, None, today)


def test_dashboard_insights_are_structured_and_role_aware(client: TestClient, factory: Factory) -> None:
    rid = factory.restaurant("Insight Thai")
    manager, cashier, kitchen = factory.manager(rid), factory.cashier(rid), factory.kitchen(rid)
    dish = factory.product(manager, factory.category(manager)["id"], "Noodles", 8000)
    _sell(client, cashier, [(dish, 3)])

    insights = client.get("/api/v1/analytics/dashboard", headers=manager.headers).json()["insights"]
    by_key = {i["key"]: i for i in insights}
    assert by_key["sales-today"]["link"] == "/analytics" and "1 order(s)" in by_key["sales-today"]["detail"]
    assert by_key["best-seller"]["title"] == "Best seller this week: Noodles"
    assert by_key["forecast"]["title"] == "No demand forecast yet" and by_key["forecast"]["action"] == "Run forecast"
    assert all(i["severity"] in {"positive", "info", "warning", "critical"} for i in insights)

    # The AI page's insight endpoint returns the same structured list.
    ai = client.get("/api/v1/ai/insights", headers=manager.headers).json()
    assert [i["key"] for i in ai["insights"]] == [i["key"] for i in insights]

    # Front-of-house staff only see what their role covers: no sales, stock or forecast figures.
    cashier_dash = client.get("/api/v1/analytics/dashboard", headers=cashier.headers).json()
    assert not {i["key"] for i in cashier_dash["insights"]} & {"sales-today", "best-seller", "forecast", "stock-risk"}
    assert cashier_dash["stock_at_risk"] == []
    assert client.get("/api/v1/analytics/dashboard", headers=kitchen.headers).status_code == 403


def test_pos_suggestions_come_from_order_history(client: TestClient, factory: Factory) -> None:
    rid = factory.restaurant("Suggest Thai")
    manager, cashier, kitchen = factory.manager(rid), factory.cashier(rid), factory.kitchen(rid)
    category = factory.category(manager)
    curry = factory.product(manager, category["id"], "Green Curry (แกงเขียวหวาน)", 13000)
    rice = factory.product(manager, category["id"], "Jasmine Rice", 2000)
    tea = factory.product(manager, category["id"], "Iced Tea", 6000)
    water = factory.product(manager, category["id"], "Water", 2000)
    for _ in range(4):
        _sell(client, cashier, [(curry, 1), (rice, 1)])
    _sell(client, cashier, [(curry, 1), (tea, 1)])  # only once together: not enough evidence
    for _ in range(3):
        _sell(client, cashier, [(tea, 1)])

    def suggest(**params) -> list[dict]:
        r = client.get("/api/v1/products/suggestions", headers=cashier.headers, params=params)
        assert r.status_code == 200, r.text
        return r.json()

    customer = client.post("/api/v1/customers", headers=cashier.headers, json={"name": "Nok"}).json()
    for _ in range(2):
        _sell(client, cashier, [(water, 1)], customer_id=customer["id"])
    # 10 orders: curry in 5, rice in 4 of them -> confidence 4/5 = 0.8, lift 0.8 / (4/10) = 2.0.
    together = suggest(product_id=[curry["id"]])
    assert [s["product_name"] for s in together] == ["Jasmine Rice"]
    assert together[0]["kind"] == "ordered_together"
    assert together[0]["reason"] == "In 80% of orders with Green Curry"
    assert together[0]["evidence"] == {"orders_together": 4, "orders_with_item": 5, "lift": 2.0}

    # Never suggest what is already in the cart, or something that cannot be sold.
    assert suggest(product_id=[curry["id"], rice["id"]]) == []
    client.patch(f"/api/v1/products/{rice['id']}", headers=manager.headers, json={"is_available": False})
    assert suggest(product_id=[curry["id"]]) == []
    client.patch(f"/api/v1/products/{rice['id']}", headers=manager.headers, json={"is_available": True})

    # A known customer's usual comes first; an empty cart falls back to what sells now.
    usual = suggest(customer_id=customer["id"])
    assert usual[0]["product_name"] == "Water" and usual[0]["kind"] == "customer_usual"
    assert usual[0]["reason"] == "Ordered on 2 visits by this customer"
    popular = suggest()  # equal sellers are ordered by name
    assert {s["kind"] for s in popular} == {"popular_now"}
    assert [s["product_name"] for s in popular][:3] == ["Green Curry (แกงเขียวหวาน)", "Iced Tea", "Jasmine Rice"]

    # Other restaurants see nothing of this history; the kitchen role cannot ring up sales.
    outsider = factory.manager(factory.restaurant("Elsewhere"))
    r = client.get("/api/v1/products/suggestions", headers=outsider.headers, params={"product_id": [curry["id"]]})
    assert r.status_code == 200 and r.json() == []
    assert client.get("/api/v1/products/suggestions", headers=kitchen.headers).status_code == 403


def test_customer_favourites_come_from_paid_orders(client: TestClient, factory: Factory) -> None:
    rid = factory.restaurant("Regulars Thai")
    manager, cashier = factory.manager(rid), factory.cashier(rid)
    category = factory.category(manager)
    tea = factory.product(manager, category["id"], "Iced Tea", 6000)
    noodles = factory.product(manager, category["id"], "Noodles", 9000)
    customer = client.post("/api/v1/customers", headers=manager.headers, json={"name": "Somchai"}).json()
    for _ in range(3):
        _sell(client, cashier, [(tea, 2)], customer_id=customer["id"])
    _sell(client, cashier, [(noodles, 1), (tea, 1)], customer_id=customer["id"])
    # An unpaid order does not count as a visit.
    client.post(
        "/api/v1/orders",
        headers=cashier.headers,
        json={
            "order_type": "TAKEAWAY",
            "items": [{"product_id": noodles["id"], "quantity": 5}],
            "customer_id": customer["id"],
        },
    )

    r = client.get(f"/api/v1/customers/{customer['id']}/favourites", headers=manager.headers)
    assert r.status_code == 200, r.text
    rows = [(f["product_name"], f["orders"], f["quantity"]) for f in r.json()]
    assert rows == [("Iced Tea", 4, 7), ("Noodles", 1, 1)]
    assert client.get(f"/api/v1/customers/{customer['id']}/favourites", headers=cashier.headers).status_code == 403
    outsider = factory.manager(factory.restaurant("Elsewhere"))
    assert client.get(f"/api/v1/customers/{customer['id']}/favourites", headers=outsider.headers).status_code == 404
