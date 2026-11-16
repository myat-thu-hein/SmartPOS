"""Inventory movements, valuation, suppliers and purchase orders."""

from __future__ import annotations

import threading

from fastapi.testclient import TestClient

from tests.conftest import Factory


def test_manual_movements_and_stock_count(client: TestClient, factory: Factory) -> None:
    rid = factory.restaurant()
    manager = factory.manager(rid)
    rice = factory.ingredient(
        manager, "Jasmine rice", "g", stock=2000, opening_unit_cost_minor="4", reorder_level="1000", safety_stock="500"
    )
    h = manager.headers
    receipt = client.post(
        "/api/v1/inventory/movements",
        headers=h,
        json={
            "ingredient_id": rice["id"],
            "movement_type": "RECEIPT",
            "quantity": "2",
            "unit": "kg",
            "unit_cost_minor": "6000",
            "reason": "Market",
        },
    )
    assert receipt.status_code == 201
    assert receipt.json()["balance_after"] == 4000.0
    detail = client.get(f"/api/v1/ingredients/{rice['id']}", headers=h).json()
    # Moving average: (2000 g * 4 + 2000 g * 6) / 4000 g = 5 satang per gram.
    assert detail["average_cost_minor"] == 5.0
    assert detail["stock_value_minor"] == 20000

    waste = client.post(
        "/api/v1/inventory/movements",
        headers=h,
        json={"ingredient_id": rice["id"], "movement_type": "WASTE", "quantity": "500", "reason": "Spilled"},
    )
    assert waste.json()["quantity"] == -500.0
    too_much = client.post(
        "/api/v1/inventory/movements",
        headers=h,
        json={
            "ingredient_id": rice["id"],
            "movement_type": "ISSUE",
            "quantity": "10",
            "unit": "kg",
            "reason": "Transfer",
        },
    )
    assert too_much.status_code == 409 and too_much.json()["error"]["code"] == "insufficient_stock"
    negative_receipt = client.post(
        "/api/v1/inventory/movements",
        headers=h,
        json={"ingredient_id": rice["id"], "movement_type": "RECEIPT", "quantity": "-5", "reason": "oops"},
    )
    assert negative_receipt.status_code == 422
    sale = client.post(
        "/api/v1/inventory/movements",
        headers=h,
        json={"ingredient_id": rice["id"], "movement_type": "SALE", "quantity": "5", "reason": "fake sale"},
    )
    assert sale.status_code == 422
    wrong_unit = client.post(
        "/api/v1/inventory/movements",
        headers=h,
        json={"ingredient_id": rice["id"], "movement_type": "RECEIPT", "quantity": "1", "unit": "L", "reason": "x" * 5},
    )
    assert wrong_unit.status_code == 422

    count = client.post(
        "/api/v1/inventory/stock-count",
        headers=h,
        json={"ingredient_id": rice["id"], "counted_quantity": "3.2", "unit": "kg"},
    )
    assert count.status_code == 200 and count.json()["quantity"] == -300.0
    assert count.json()["balance_after"] == 3200.0
    same = client.post(
        "/api/v1/inventory/stock-count", headers=h, json={"ingredient_id": rice["id"], "counted_quantity": "3200"}
    )
    assert same.status_code == 200 and same.json() is None

    history = client.get("/api/v1/inventory/movements", params={"ingredient_id": rice["id"]}, headers=h).json()
    assert history["total"] == 4
    assert [m["movement_type"] for m in history["items"]] == ["ADJUSTMENT", "WASTE", "RECEIPT", "OPENING"]
    assert history["items"][0]["actor_name"]

    summary = client.get("/api/v1/inventory/summary", headers=h).json()
    assert summary["ingredient_count"] == 1 and summary["low_stock_count"] == 0
    client.patch(f"/api/v1/ingredients/{rice['id']}", headers=h, json={"reorder_level": "5000"})
    low = client.get("/api/v1/inventory/low-stock", headers=h).json()
    assert [i["name"] for i in low] == ["Jasmine rice"] and low[0]["is_low_stock"] is True


def test_cashier_and_kitchen_cannot_touch_inventory(client: TestClient, factory: Factory) -> None:
    rid = factory.restaurant()
    manager = factory.manager(rid)
    rice = factory.ingredient(manager, "Rice", "g", stock=100)
    for actor in (factory.cashier(rid), factory.kitchen(rid)):
        assert client.get("/api/v1/ingredients", headers=actor.headers).status_code == 403
        r = client.post(
            "/api/v1/inventory/movements",
            headers=actor.headers,
            json={"ingredient_id": rice["id"], "movement_type": "WASTE", "quantity": "1", "reason": "test"},
        )
        assert r.status_code == 403


def _setup_supplier(client: TestClient, factory: Factory):
    rid = factory.restaurant()
    manager = factory.manager(rid)
    shrimp = factory.ingredient(manager, "Shrimp", "g", stock=0)
    egg = factory.ingredient(manager, "Egg", "piece", stock=0, units=[{"unit_name": "tray", "factor_to_base": "30"}])
    supplier = client.post(
        "/api/v1/suppliers",
        headers=manager.headers,
        json={"name": "Talad Thai Wholesale", "phone": "021234567", "lead_time_days": 2},
    ).json()
    link = client.post(
        f"/api/v1/suppliers/{supplier['id']}/ingredients",
        headers=manager.headers,
        json={
            "ingredient_id": shrimp["id"],
            "supplier_sku": "SHR-1KG",
            "unit_cost_minor": "40000",
            "unit": "kg",
            "min_order_quantity": "1",
            "lead_time_days": 1,
        },
    )
    assert link.status_code == 201, link.text
    assert link.json()["unit_cost_minor"] == 40.0 and link.json()["min_order_quantity"] == 1000.0
    return rid, manager, supplier, shrimp, egg


def test_purchase_order_lifecycle_with_partial_receipts(client: TestClient, factory: Factory) -> None:
    _, manager, supplier, shrimp, egg = _setup_supplier(client, factory)
    h = manager.headers
    po = client.post(
        "/api/v1/purchase-orders",
        headers=h,
        json={
            "supplier_id": supplier["id"],
            "expected_delivery_date": "2026-10-30",
            "items": [
                {"ingredient_id": shrimp["id"], "quantity": "5", "unit": "kg"},
                {"ingredient_id": egg["id"], "quantity": "4", "unit": "tray", "unit_cost_minor": "12000"},
            ],
        },
    )
    assert po.status_code == 201, po.text
    po = po.json()
    assert po["status"] == "DRAFT" and po["display_number"] == "PO-00001"
    by_name = {i["ingredient_name"]: i for i in po["items"]}
    assert by_name["Shrimp"]["quantity_ordered"] == 5000.0 and by_name["Shrimp"]["unit_cost_minor"] == 40.0
    assert by_name["Egg"]["quantity_ordered"] == 120.0 and by_name["Egg"]["unit_cost_minor"] == 400.0
    assert po["estimated_total_minor"] == 5000 * 40 + 120 * 400

    receive_draft = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        headers={**h, "Idempotency-Key": "recv-draft-1"},
        json={"lines": [{"item_id": by_name["Shrimp"]["id"], "quantity": "1"}]},
    )
    assert receive_draft.status_code == 409
    edited = client.patch(f"/api/v1/purchase-orders/{po['id']}", headers=h, json={"notes": "Call before delivery"})
    assert edited.json()["notes"] == "Call before delivery"
    submitted = client.post(f"/api/v1/purchase-orders/{po['id']}/submit", headers=h).json()
    assert submitted["status"] == "SUBMITTED"
    assert client.patch(f"/api/v1/purchase-orders/{po['id']}", headers=h, json={"notes": "x"}).status_code == 409
    missing_key = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        headers=h,
        json={"lines": [{"item_id": by_name["Shrimp"]["id"], "quantity": "1"}]},
    )
    assert missing_key.status_code == 422

    first = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        headers={**h, "Idempotency-Key": "recv-0001"},
        json={
            "lines": [{"item_id": by_name["Shrimp"]["id"], "quantity": "3", "unit": "kg", "unit_cost_minor": "42000"}]
        },
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "PARTIALLY_RECEIVED"
    dup = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        headers={**h, "Idempotency-Key": "recv-0001"},
        json={"lines": [{"item_id": by_name["Shrimp"]["id"], "quantity": "3", "unit": "kg"}]},
    )
    assert dup.headers.get("Idempotent-Replayed") == "true"
    shrimp_now = client.get(f"/api/v1/ingredients/{shrimp['id']}", headers=h).json()
    assert shrimp_now["current_stock"] == 3000.0 and shrimp_now["average_cost_minor"] == 42.0

    over = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        headers={**h, "Idempotency-Key": "recv-0002"},
        json={"lines": [{"item_id": by_name["Shrimp"]["id"], "quantity": "2.5", "unit": "kg"}]},
    )
    assert over.status_code == 422 and over.json()["error"]["code"] == "over_receipt"
    final = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        headers={**h, "Idempotency-Key": "recv-0003"},
        json={
            "lines": [
                {"item_id": by_name["Shrimp"]["id"], "quantity": "2", "unit": "kg"},
                {"item_id": by_name["Egg"]["id"], "quantity": "4"},
            ]
        },
    )
    assert final.json()["status"] == "RECEIVED" and len(final.json()["receipts"]) == 2
    movements = client.get("/api/v1/inventory/movements", headers=h, params={"purchase_order_id": po["id"]}).json()
    assert movements["total"] == 3
    assert {m["movement_type"] for m in movements["items"]} == {"PURCHASE_RECEIPT"}
    assert (
        client.post(f"/api/v1/purchase-orders/{po['id']}/cancel", headers=h, json={"reason": "late"}).status_code == 409
    )


def test_concurrent_duplicate_receipts(client: TestClient, factory: Factory) -> None:
    _, manager, supplier, shrimp, _ = _setup_supplier(client, factory)
    po = client.post(
        "/api/v1/purchase-orders",
        headers=manager.headers,
        json={"supplier_id": supplier["id"], "items": [{"ingredient_id": shrimp["id"], "quantity": "1000"}]},
    ).json()
    client.post(f"/api/v1/purchase-orders/{po['id']}/submit", headers=manager.headers)
    item_id = po["items"][0]["id"]
    codes: list[int] = []

    def receive() -> None:
        r = client.post(
            f"/api/v1/purchase-orders/{po['id']}/receive",
            headers={**manager.headers, "Idempotency-Key": "same-delivery"},
            json={"lines": [{"item_id": item_id, "quantity": "600"}]},
        )
        codes.append(r.status_code)

    threads = [threading.Thread(target=receive) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert codes == [200, 200, 200]
    detail = client.get(f"/api/v1/ingredients/{shrimp['id']}", headers=manager.headers).json()
    assert detail["current_stock"] == 600.0


def test_cancel_and_permissions(client: TestClient, factory: Factory) -> None:
    rid, manager, supplier, shrimp, _ = _setup_supplier(client, factory)
    cashier = factory.cashier(rid)
    denied = client.post(
        "/api/v1/purchase-orders",
        headers=cashier.headers,
        json={"supplier_id": supplier["id"], "items": [{"ingredient_id": shrimp["id"], "quantity": "1"}]},
    )
    assert denied.status_code == 403
    assert client.get("/api/v1/suppliers", headers=cashier.headers).status_code == 403
    po = client.post(
        "/api/v1/purchase-orders",
        headers=manager.headers,
        json={"supplier_id": supplier["id"], "items": [{"ingredient_id": shrimp["id"], "quantity": "1"}]},
    ).json()
    cancelled = client.post(
        f"/api/v1/purchase-orders/{po['id']}/cancel", headers=manager.headers, json={"reason": "Supplier closed"}
    )
    assert cancelled.json()["status"] == "CANCELLED"
    listed = client.get("/api/v1/purchase-orders", params={"status": "CANCELLED"}, headers=manager.headers).json()
    assert listed["total"] == 1
    suppliers = client.get("/api/v1/suppliers", headers=manager.headers).json()
    assert suppliers[0]["ingredient_count"] == 1
