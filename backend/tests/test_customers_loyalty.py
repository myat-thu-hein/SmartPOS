"""Customers and the loyalty ledger."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import Customer, LoyaltyTransaction
from tests.conftest import Factory


def _setup(client: TestClient, factory: Factory):
    # Inclusive pricing, 1 point per 25 THB, 1 point = 1 THB.
    rid = factory.restaurant("Loyal Thai", prices_include_tax=True, tax_rate_bps=700)
    manager, cashier = factory.manager(rid), factory.cashier(rid)
    category = factory.category(manager)
    product = factory.product(manager, category["id"], "Green curry", 15000)
    return rid, manager, cashier, product, factory.payment_method_id(manager)


def _order(client: TestClient, actor, product, customer_id, points: int = 0, confirm: bool = True) -> dict:
    payload = {
        "order_type": "TAKEAWAY",
        "items": [{"product_id": product["id"], "quantity": 2}],
        "customer_id": customer_id,
        "confirm": confirm,
    }
    if points:
        payload["loyalty_points_to_redeem"] = points
    r = client.post("/api/v1/orders", json=payload, headers=actor.headers)
    assert r.status_code == 201, r.text
    return r.json()


def _pay(client: TestClient, actor, order: dict, method: str) -> dict:
    r = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=actor.headers,
        json={"payment_method_id": method, "amount_minor": order["total_minor"]},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _ledger_consistent(db, customer_id: str) -> int:
    db.expire_all()
    customer = db.get(Customer, uuid.UUID(customer_id))
    total = db.scalar(
        select(func.coalesce(func.sum(LoyaltyTransaction.points), 0)).where(
            LoyaltyTransaction.customer_id == customer.id
        )
    )
    assert total == customer.loyalty_balance
    return customer.loyalty_balance


def test_customer_privacy_by_role(client: TestClient, factory: Factory) -> None:
    rid, manager, cashier, _, _ = _setup(client, factory)
    created = client.post(
        "/api/v1/customers",
        headers=cashier.headers,
        json={
            "name": "Somchai",
            "phone": "081-234-5678",
            "email": "somchai@example.com",
            "notes": "allergic to peanuts",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["phone_masked"] == "••••••5678" and "email" not in body and "notes" not in body
    duplicate = client.post("/api/v1/customers", headers=cashier.headers, json={"name": "Other", "phone": "0812345678"})
    assert duplicate.status_code == 409
    found = client.get("/api/v1/customers", params={"search": "5678"}, headers=cashier.headers).json()
    assert found["total"] == 1 and "phone" not in found["items"][0]
    full = client.get(f"/api/v1/customers/{body['id']}", headers=manager.headers).json()
    assert full["phone"] == "0812345678" and full["email"] == "somchai@example.com"
    assert (
        client.patch(f"/api/v1/customers/{body['id']}", headers=cashier.headers, json={"name": "x"}).status_code == 403
    )
    anonymised = client.post(f"/api/v1/customers/{body['id']}/anonymise", headers=manager.headers).json()
    assert anonymised["phone"] is None and anonymised["name"] == "Deleted customer"
    kitchen = factory.kitchen(rid)
    assert client.get("/api/v1/customers", headers=kitchen.headers).status_code == 403


def test_earn_redeem_cancel_and_refund_reversal(client: TestClient, factory: Factory, db) -> None:
    _, manager, cashier, product, cash = _setup(client, factory)
    customer = client.post("/api/v1/customers", headers=cashier.headers, json={"name": "Nok", "phone": "0899999999"})
    cid = customer.json()["id"]

    first = _order(client, cashier, product, cid)  # 300.00 THB
    assert first["total_minor"] == 30000
    paid = _pay(client, cashier, first, cash)
    assert paid["payment_status"] == "PAID"
    assert _ledger_consistent(db, cid) == 12  # 300 / 25

    receipt = client.get(f"/api/v1/orders/{first['id']}/receipt", headers=cashier.headers).json()
    assert receipt["loyalty_points_earned"] == 12

    too_many = client.post(
        "/api/v1/orders",
        headers=cashier.headers,
        json={
            "order_type": "TAKEAWAY",
            "items": [{"product_id": product["id"], "quantity": 1}],
            "customer_id": cid,
            "loyalty_points_to_redeem": 13,
        },
    )
    assert too_many.status_code == 422 and too_many.json()["error"]["code"] == "insufficient_points"

    redeem = _order(client, cashier, product, cid, points=10)
    assert redeem["loyalty_discount_minor"] == 1000 and redeem["total_minor"] == 29000
    assert _ledger_consistent(db, cid) == 2
    locked = client.patch(
        f"/api/v1/orders/{redeem['id']}", headers=cashier.headers, json={"loyalty_points_to_redeem": 0}
    )
    assert locked.status_code == 409
    cancel = client.post(f"/api/v1/orders/{redeem['id']}/cancel", headers=manager.headers, json={"reason": "left"})
    assert cancel.status_code == 200
    assert _ledger_consistent(db, cid) == 12

    third = _order(client, cashier, product, cid)
    paid3 = _pay(client, cashier, third, cash)
    assert _ledger_consistent(db, cid) == 24
    payment_id = paid3["payments"][0]["id"]
    client.post(
        f"/api/v1/orders/{third['id']}/refunds",
        headers=manager.headers,
        json={"payment_id": payment_id, "amount_minor": 15000, "reason": "half returned"},
    )
    assert _ledger_consistent(db, cid) == 18  # half of 12 earned points reversed
    client.post(
        f"/api/v1/orders/{third['id']}/refunds",
        headers=manager.headers,
        json={"payment_id": payment_id, "amount_minor": 15000, "reason": "rest returned"},
    )
    assert _ledger_consistent(db, cid) == 12

    history = client.get(f"/api/v1/loyalty/customers/{cid}/transactions", headers=manager.headers).json()
    types = [t["transaction_type"] for t in reversed(history["items"])]
    assert types == ["EARN", "REDEEM", "REVERSAL", "EARN", "REVERSAL", "REVERSAL"]

    stats = client.get(f"/api/v1/customers/{cid}", headers=manager.headers).json()
    assert stats["order_count"] == 2 and stats["total_spent_minor"] == 30000


def test_manual_adjustment_and_permissions(client: TestClient, factory: Factory, db) -> None:
    _, manager, cashier, _, _ = _setup(client, factory)
    cid = client.post("/api/v1/customers", headers=manager.headers, json={"name": "Ploy"}).json()["id"]
    assert (
        client.post(
            f"/api/v1/loyalty/customers/{cid}/adjust", headers=cashier.headers, json={"points": 50, "reason": "welcome"}
        ).status_code
        == 403
    )
    ok = client.post(
        f"/api/v1/loyalty/customers/{cid}/adjust",
        headers=manager.headers,
        json={"points": 50, "reason": "welcome bonus"},
    )
    assert ok.json()["loyalty_balance"] == 50
    negative = client.post(
        f"/api/v1/loyalty/customers/{cid}/adjust", headers=manager.headers, json={"points": -60, "reason": "correction"}
    )
    assert negative.status_code == 422
    assert _ledger_consistent(db, cid) == 50
    settings = client.get("/api/v1/loyalty/settings", headers=cashier.headers).json()
    assert settings["loyalty_enabled"] is True and "25.00" in settings["description"]


def test_guest_orders_do_not_earn(client: TestClient, factory: Factory, db) -> None:
    _, _, cashier, product, cash = _setup(client, factory)
    order = _order(client, cashier, product, None)
    _pay(client, cashier, order, cash)
    assert db.scalar(select(func.count()).select_from(LoyaltyTransaction)) == 0
