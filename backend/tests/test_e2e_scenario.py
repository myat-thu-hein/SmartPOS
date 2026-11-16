"""End-to-end business scenario through the public API.

One restaurant is set up from nothing by an administrator, runs a service
(order, kitchen, payment, loyalty, refund), forecasts demand, turns reorder
suggestions into a purchase order and receives it, while a second restaurant
stays isolated. Every step uses the same HTTP API as the web app.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import InventoryMovement
from tests.conftest import Factory
from tests.test_forecasting import _seed_history

STRONG = "Scenario-pass-26"


def _login(client: TestClient, email: str, restaurant_id: str | None = None) -> dict[str, str]:
    r = client.post("/api/v1/auth/token", json={"email": email, "password": STRONG})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    if restaurant_id:
        headers["X-Restaurant-ID"] = restaurant_id
    return headers


def _ok(response, status: int = 200) -> dict:
    assert response.status_code == status, response.text
    return response.json()


def test_restaurant_lifecycle(client: TestClient, factory: Factory, db) -> None:
    # 1. A platform administrator creates the manager account and the restaurant.
    admin = factory.admin()
    _ok(
        client.post(
            "/api/v1/users/platform",
            headers=admin.headers,
            json={"email": "nok@baan-e2e.co.th", "full_name": "Nok Manager", "password": STRONG},
        ),
        201,
    )
    restaurant = _ok(
        client.post(
            "/api/v1/restaurants",
            headers=admin.headers,
            json={"name": "Baan E2E", "timezone": "Asia/Bangkok", "manager_email": "nok@baan-e2e.co.th"},
        ),
        201,
    )
    rid = restaurant["id"]
    manager = _login(client, "nok@baan-e2e.co.th", rid)

    # 2. The manager configures pricing: VAT 7% included in prices, 10% service charge for dine-in.
    settings = _ok(
        client.patch(
            "/api/v1/restaurants/current",
            headers=manager,
            json={"tax_rate_bps": 700, "prices_include_tax": True, "service_charge_bps": 1000, "loyalty_enabled": True},
        )
    )
    assert settings["service_charge_dine_in_only"] is True

    # 3. Staff accounts. Managers cannot create other managers.
    for email, role in (("chai@baan-e2e.co.th", "CASHIER"), ("kai@baan-e2e.co.th", "KITCHEN")):
        _ok(
            client.post(
                "/api/v1/users",
                headers=manager,
                json={"email": email, "full_name": role.title(), "password": STRONG, "role": role},
            ),
            201,
        )
    denied = client.post(
        "/api/v1/users",
        headers=manager,
        json={"email": "boss@baan-e2e.co.th", "full_name": "Boss", "password": STRONG, "role": "MANAGER"},
    )
    assert denied.status_code == 403
    cashier = _login(client, "chai@baan-e2e.co.th", rid)
    kitchen = _login(client, "kai@baan-e2e.co.th", rid)

    # 4. Supplier, ingredients with opening stock and cost, and a price list with a minimum order.
    supplier = _ok(
        client.post("/api/v1/suppliers", headers=manager, json={"name": "Talad Thai", "lead_time_days": 2}), 201
    )
    noodles = _ok(
        client.post(
            "/api/v1/ingredients",
            headers=manager,
            json={
                "name": "Rice noodles",
                "base_unit": "g",
                "opening_stock": "5000",
                "opening_unit_cost_minor": "6",  # per gram = 60.00 THB/kg
                "reorder_level": "2000",
                "safety_stock": "1000",
                "default_supplier_id": supplier["id"],
            },
        ),
        201,
    )
    assert noodles["current_stock"] == 5000 and noodles["average_cost_minor"] == 6
    egg = _ok(
        client.post(
            "/api/v1/ingredients",
            headers=manager,
            json={"name": "Egg", "base_unit": "piece", "opening_stock": "30", "opening_unit_cost_minor": "400"},
        ),
        201,
    )
    _ok(
        client.post(
            f"/api/v1/suppliers/{supplier['id']}/ingredients",
            headers=manager,
            json={
                "ingredient_id": noodles["id"],
                "unit_cost_minor": "6000",
                "unit": "kg",
                "min_order_quantity": "1",
                "lead_time_days": 1,
            },
        ),
        201,
    )

    # 5. Menu with a modifier that consumes stock, and a recipe.
    category = _ok(client.post("/api/v1/categories", headers=manager, json={"name": "Noodles"}), 201)
    extras = _ok(
        client.post(
            "/api/v1/modifiers/groups",
            headers=manager,
            json={
                "name": "Extras",
                "selection_type": "MULTIPLE",
                "min_select": 0,
                "max_select": 2,
                "options": [
                    {
                        "name": "Extra egg",
                        "price_delta_minor": 1000,
                        "ingredient_id": egg["id"],
                        "ingredient_quantity": "1",
                    }
                ],
            },
        ),
        201,
    )
    pad_thai = _ok(
        client.post(
            "/api/v1/products",
            headers=manager,
            json={"name": "Pad Thai", "category_id": category["id"], "price_minor": 12000},
        ),
        201,
    )
    _ok(
        client.put(
            f"/api/v1/products/{pad_thai['id']}/modifier-groups",
            headers=manager,
            json={"modifier_group_ids": [extras["id"]]},
        )
    )
    recipe = _ok(
        client.put(
            f"/api/v1/recipes/products/{pad_thai['id']}",
            headers=manager,
            json={
                "items": [
                    {"ingredient_id": noodles["id"], "quantity": "150", "unit": "g"},
                    {"ingredient_id": egg["id"], "quantity": "1"},
                ]
            },
        )
    )
    assert recipe["version"] == 1 and recipe["estimated_cost_minor"] == 900 + 400
    table = _ok(client.post("/api/v1/tables", headers=manager, json={"name": "T1", "capacity": 4}), 201)

    # 6. The cashier registers a customer and sends a dine-in order to the kitchen.
    customer = _ok(
        client.post("/api/v1/customers", headers=cashier, json={"name": "Somchai", "phone": "0812345678"}), 201
    )
    order = _ok(
        client.post(
            "/api/v1/orders",
            headers={**cashier, "Idempotency-Key": "e2e-order-0001"},
            json={
                "order_type": "DINE_IN",
                "table_id": table["id"],
                "customer_id": customer["id"],
                "items": [
                    {
                        "product_id": pad_thai["id"],
                        "quantity": 2,
                        "modifier_option_ids": [extras["options"][0]["id"]],
                        "notes": "no peanuts",
                    }
                ],
                "confirm": True,
            },
        ),
        201,
    )
    # (120 + 10) x 2 = 260.00 incl. VAT, plus 10% service charge = 286.00.
    assert order["status"] == "CONFIRMED" and order["subtotal_minor"] == 26000 and order["total_minor"] == 28600
    noodles_now = _ok(client.get(f"/api/v1/ingredients/{noodles['id']}", headers=manager))
    egg_now = _ok(client.get(f"/api/v1/ingredients/{egg['id']}", headers=manager))
    assert noodles_now["current_stock"] == 5000 - 300 and egg_now["current_stock"] == 30 - 4  # 2 recipe + 2 extra
    # The deduction is recorded as SALE movements linked to the order and the cashier who confirmed it.
    movements = _ok(client.get("/api/v1/inventory/movements", headers=manager, params={"order_id": order["id"]}))
    by_ingredient = {m["ingredient_id"]: m for m in movements["items"]}
    assert {m["movement_type"] for m in movements["items"]} == {"SALE"}
    assert by_ingredient[noodles["id"]]["quantity"] == -300 and by_ingredient[egg["id"]]["quantity"] == -4
    assert by_ingredient[noodles["id"]]["balance_after"] == 4700
    assert all(m["actor_name"] == "Cashier" for m in movements["items"])

    # 7. The kitchen works the ticket; it never sees prices.
    tickets = _ok(client.get("/api/v1/kitchen/orders", headers=kitchen))
    assert [t["order_id"] for t in tickets] == [order["id"]] and "total_minor" not in tickets[0]
    for status in ("PREPARING", "READY"):
        _ok(client.post(f"/api/v1/kitchen/orders/{order['id']}/status", headers=kitchen, json={"status": status}))

    # 8. Cash payment; a retried request with the same key does not charge twice.
    pay_headers = {**cashier, "Idempotency-Key": "e2e-pay-0001"}
    payment = {
        "payment_method_id": factory.payment_method_id(factory.manager(rid), "CASH"),
        "amount_minor": 28600,
        "amount_tendered_minor": 30000,
    }
    paid = _ok(client.post(f"/api/v1/orders/{order['id']}/payments", headers=pay_headers, json=payment), 201)
    retry = _ok(client.post(f"/api/v1/orders/{order['id']}/payments", headers=pay_headers, json=payment))
    assert paid["payment_status"] == "PAID" and retry["amount_paid_minor"] == 28600 and len(retry["payments"]) == 1
    assert paid["payments"][0]["change_minor"] == 1400
    # The kitchen completes the paid order, and the table can then be closed.
    done = _ok(
        client.post(f"/api/v1/kitchen/orders/{order['id']}/status", headers=kitchen, json={"status": "COMPLETED"})
    )
    assert done["kitchen_status"] == "COMPLETED"
    assert _ok(client.get(f"/api/v1/orders/{order['id']}", headers=cashier))["status"] == "COMPLETED"
    assert _ok(client.post(f"/api/v1/tables/{table['id']}/close", headers=cashier))["status"] == "CLEANING"
    receipt = _ok(client.get(f"/api/v1/orders/{order['id']}/receipt", headers=cashier))
    assert receipt["simulated_payment_notice"] and receipt["loyalty_points_earned"] > 0
    assert (
        _ok(client.get(f"/api/v1/customers/{customer['id']}", headers=cashier))["loyalty_balance"]
        == receipt["loyalty_points_earned"]
    )

    # 9. Only a manager may refund.
    refund = {"payment_id": paid["payments"][0]["id"], "amount_minor": 5000, "reason": "Late dish"}
    assert client.post(f"/api/v1/orders/{order['id']}/refunds", headers=cashier, json=refund).status_code == 403
    refunded = _ok(
        client.post(
            f"/api/v1/orders/{order['id']}/refunds", headers={**manager, "Idempotency-Key": "e2e-refund-1"}, json=refund
        ),
        201,
    )
    assert refunded["payment_status"] == "PARTIALLY_REFUNDED"

    # 10. Analytics and reports reflect the sale and the refund.
    summary = _ok(client.get("/api/v1/analytics/summary", headers=manager))
    assert summary["order_count"] == 1 and summary["gross_sales_minor"] == 26000
    assert summary["refunds_minor"] == 5000 and summary["net_sales_minor"] == 21000
    report = client.get("/api/v1/reports/orders.csv", headers=manager)
    assert report.status_code == 200 and order["display_number"] in report.text
    assert client.get("/api/v1/reports/orders.csv", headers=cashier).status_code == 403

    # 11. Forecast from history, then reorder suggestions that only become a DRAFT purchase order.
    _seed_history(db, rid, pad_thai, days=60)
    run = _ok(client.post("/api/v1/forecast/runs", headers=manager, json={"horizon_days": 7}), 201)
    assert run["ingredients"] and {m["model_name"] for m in run["metrics"]} >= {"moving_average", "dow_average"}
    points = run["products"][0]["points"]
    assert [p["horizon_day"] for p in points] == [1, 2, 3, 4, 5, 6, 7]  # next-day and seven-day forecast
    assert all(m["mae"] is not None for m in run["metrics"] if m["evaluation_points"])
    generated = _ok(client.post("/api/v1/recommendations/generate", headers=manager, json={"review_period_days": 7}))
    suggestion = next(r for r in generated["created"] if r["ingredient_id"] == noodles["id"])
    assert suggestion["status"] == "PENDING" and suggestion["supplier_id"] == supplier["id"]
    assert Decimal(str(suggestion["suggested_quantity"])) % 1000 == 0  # rounded up to whole kg (minimum order 1 kg)
    assert _ok(client.get("/api/v1/purchase-orders", headers=manager))["total"] == 0  # nothing ordered automatically
    # Approval is a manager action only.
    assert (
        client.post(f"/api/v1/recommendations/{suggestion['id']}/approve", headers=cashier, json={}).status_code == 403
    )
    approved = _ok(
        client.post(f"/api/v1/recommendations/{suggestion['id']}/approve", headers=manager, json={"note": "ok"})
    )
    assert approved["status"] == "APPROVED" and approved["reviewer_name"] == "Nok Manager"
    created = _ok(
        client.post(
            "/api/v1/recommendations/purchase-orders", headers=manager, json={"recommendation_ids": [suggestion["id"]]}
        )
    )
    po = _ok(client.get(f"/api/v1/purchase-orders/{created[0]['purchase_order_id']}", headers=manager))
    assert po["status"] == "DRAFT" and po["submitted_at"] is None

    # 12. Submit, then receive in two deliveries; stock follows the ledger exactly.
    _ok(client.post(f"/api/v1/purchase-orders/{po['id']}/submit", headers=manager))
    item = po["items"][0]
    ordered = Decimal(str(item["quantity_ordered"]))
    stock_before = Decimal(
        str(_ok(client.get(f"/api/v1/ingredients/{noodles['id']}", headers=manager))["current_stock"])
    )
    first = _ok(
        client.post(
            f"/api/v1/purchase-orders/{po['id']}/receive",
            headers={**manager, "Idempotency-Key": "e2e-receive-1"},
            json={"lines": [{"item_id": item["id"], "quantity": "1000", "unit": "g"}], "notes": "Short delivery"},
        )
    )
    assert first["status"] == "PARTIALLY_RECEIVED"
    rest = str(ordered - 1000)
    second = _ok(
        client.post(
            f"/api/v1/purchase-orders/{po['id']}/receive",
            headers={**manager, "Idempotency-Key": "e2e-receive-2"},
            json={"lines": [{"item_id": item["id"], "quantity": rest, "unit": "g"}]},
        )
    )
    assert second["status"] == "RECEIVED"
    stock_after = Decimal(
        str(_ok(client.get(f"/api/v1/ingredients/{noodles['id']}", headers=manager))["current_stock"])
    )
    assert stock_after == stock_before + ordered
    ledger = db.scalar(
        select(func.sum(InventoryMovement.quantity)).where(InventoryMovement.ingredient_id == noodles["id"])
    )
    assert ledger == stock_after

    # 13. The assistant (rule-based without an API key) answers from this restaurant's data only.
    answer = _ok(client.post("/api/v1/ai/chat", headers=manager, json={"message": "What should we reorder?"}))
    assert answer["mode"] == "offline" and answer["tools_used"][0]["name"] == "get_reorder_recommendations"
    assert client.post("/api/v1/ai/chat", headers=cashier, json={"message": "sales today"}).status_code == 403

    # 14. Staff cannot perform manager operations.
    forbidden = [
        ("post", "/api/v1/products", cashier, {"name": "Free", "category_id": category["id"], "price_minor": 0}),
        ("post", "/api/v1/products", kitchen, {"name": "Free", "category_id": category["id"], "price_minor": 0}),
        ("patch", "/api/v1/restaurants/current", cashier, {"tax_rate_bps": 0}),
        ("post", "/api/v1/purchase-orders", cashier, {"supplier_id": supplier["id"], "items": []}),
        ("post", "/api/v1/inventory/movements", kitchen, {"ingredient_id": egg["id"], "movement_type": "WASTE"}),
        ("post", "/api/v1/forecast/runs", cashier, {}),
        ("get", "/api/v1/analytics/summary", kitchen, None),
        ("get", "/api/v1/users", cashier, None),
    ]
    for method, url, headers, body in forbidden:
        response = getattr(client, method)(url, headers=headers, **({"json": body} if body is not None else {}))
        assert response.status_code == 403, (method, url, response.status_code)

    # Another restaurant cannot see any of it, even with a valid ID.
    other_rid = factory.restaurant("Other Kitchen")
    outsider = factory.manager(other_rid)
    assert client.get(f"/api/v1/orders/{order['id']}", headers=outsider.headers).status_code == 404
    assert client.get(f"/api/v1/customers/{customer['id']}", headers=outsider.headers).status_code == 404
    assert client.get("/api/v1/orders", headers={**outsider.headers, "X-Restaurant-ID": rid}).status_code == 403
    assert _ok(client.get("/api/v1/analytics/summary", headers=outsider.headers))["order_count"] == 0
