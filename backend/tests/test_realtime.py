"""Live-update feed, stream and notifications."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.core.config import get_settings
from tests.conftest import Factory


def _cursor(client: TestClient, actor) -> int:
    r = client.get("/api/v1/events", headers=actor.headers)
    assert r.status_code == 200 and r.json()["events"] == []
    return r.json()["cursor"]


def _events(client: TestClient, actor, after: int) -> list[dict]:
    r = client.get("/api/v1/events", headers=actor.headers, params={"after": after})
    assert r.status_code == 200, r.text
    return r.json()["events"]


def _setup(factory: Factory, stock: int = 1000, reorder_level: str = "0"):
    rid = factory.restaurant("Live Thai")
    manager, cashier, kitchen = factory.manager(rid), factory.cashier(rid), factory.kitchen(rid)
    rice = factory.ingredient(manager, "Rice", "g", stock=stock, reorder_level=reorder_level)
    category = factory.category(manager)
    dish = factory.product(manager, category["id"], "Rice bowl", 6000)
    factory.recipe(manager, dish["id"], [{"ingredient_id": rice["id"], "quantity": "200", "unit": "g"}])
    return rid, manager, cashier, kitchen, rice, dish


def _sell(client: TestClient, cashier, dish, quantity: int = 1):
    return client.post(
        "/api/v1/orders",
        headers=cashier.headers,
        json={"order_type": "TAKEAWAY", "items": [{"product_id": dish["id"], "quantity": quantity}], "confirm": True},
    )


def test_feed_carries_order_and_stock_changes_by_role(client: TestClient, factory: Factory) -> None:
    _, manager, cashier, kitchen, rice, dish = _setup(factory)
    start = _cursor(client, manager)
    order = _sell(client, cashier, dish).json()

    manager_events = _events(client, manager, start)
    types = [e["type"] for e in manager_events]
    assert "order.confirmed" in types and "stock.changed" in types
    confirmed = next(e for e in manager_events if e["type"] == "order.confirmed")
    assert confirmed["entity_id"] == order["id"]
    assert confirmed["data"]["display_number"] == order["display_number"]
    assert confirmed["actor_user_id"] == str(cashier.user_id)
    assert "total_minor" not in json.dumps(confirmed["data"])  # no money amounts on the feed
    stock = next(e for e in manager_events if e["type"] == "stock.changed")
    assert stock["data"]["ingredient_ids"] == [rice["id"]]

    # The kitchen sees orders but not inventory; ids keep increasing so clients can resume.
    kitchen_types = [e["type"] for e in _events(client, kitchen, start)]
    assert "order.confirmed" in kitchen_types and "stock.changed" not in kitchen_types
    assert [e["id"] for e in manager_events] == sorted(e["id"] for e in manager_events)

    client.post(f"/api/v1/kitchen/orders/{order['id']}/status", headers=kitchen.headers, json={"status": "PREPARING"})
    latest = manager_events[-1]["id"]
    assert [e["type"] for e in _events(client, manager, latest)] == ["order.preparing"]


def test_feed_is_tenant_isolated_and_rolled_back_changes_emit_nothing(client: TestClient, factory: Factory) -> None:
    _, manager, cashier, _, _, dish = _setup(factory, stock=100)  # one bowl needs 200 g
    other_rid = factory.restaurant("Elsewhere")
    outsider = factory.manager(other_rid)
    start, outsider_start = _cursor(client, manager), _cursor(client, outsider)

    refused = _sell(client, cashier, dish)
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "insufficient_stock"
    assert _events(client, manager, start) == []  # the failed confirmation left no event

    client.post(
        "/api/v1/orders",
        headers=cashier.headers,
        json={"order_type": "TAKEAWAY", "items": [{"product_id": dish["id"], "quantity": 1}]},
    )
    assert [e["type"] for e in _events(client, manager, start)] == ["order.created"]
    assert _events(client, outsider, outsider_start) == []


def test_low_and_out_of_stock_alerts_fire_once_per_crossing(client: TestClient, factory: Factory) -> None:
    _, manager, cashier, _, rice, dish = _setup(factory, stock=1000, reorder_level="500")
    for _ in range(2):  # 1000 -> 600 g: still above the reorder level
        _sell(client, cashier, dish, 1)
    assert client.get("/api/v1/notifications", headers=manager.headers).json()["items"] == []

    _sell(client, cashier, dish, 1)  # 600 -> 400 g: crosses 500
    _sell(client, cashier, dish, 1)  # 400 -> 200 g: still low, no repeat
    notes = client.get("/api/v1/notifications", headers=manager.headers).json()
    assert [n["kind"] for n in notes["items"]] == ["LOW_STOCK"]
    low = notes["items"][0]
    assert low["title"] == "Rice is running low" and "200 g left" not in low["body"] and "400 g left" in low["body"]
    assert low["severity"] == "warning" and low["entity_id"] == rice["id"] and notes["unread_count"] == 1

    _sell(client, cashier, dish, 1)  # 200 -> 0 g
    notes = client.get("/api/v1/notifications", headers=manager.headers).json()
    assert [n["kind"] for n in notes["items"]] == ["OUT_OF_STOCK", "LOW_STOCK"]
    assert notes["items"][0]["severity"] == "critical" and notes["unread_count"] == 2

    # Stock alerts are for inventory staff only, and reading is per user.
    assert client.get("/api/v1/notifications", headers=cashier.headers).json() == {"items": [], "unread_count": 0}
    assert client.post("/api/v1/notifications/read", headers=manager.headers).status_code == 200
    after_read = client.get("/api/v1/notifications", headers=manager.headers).json()
    assert after_read["unread_count"] == 0 and not any(n["unread"] for n in after_read["items"])

    # The alert also travelled on the live feed.
    created = [e for e in _events(client, manager, 0) if e["type"] == "notification.created"]
    assert [e["data"]["kind"] for e in created] == ["LOW_STOCK", "OUT_OF_STOCK"]


def test_delivery_creates_a_notification(client: TestClient, factory: Factory) -> None:
    _, manager, _, _, rice, _ = _setup(factory)
    supplier = client.post("/api/v1/suppliers", headers=manager.headers, json={"name": "Market"}).json()
    po = client.post(
        "/api/v1/purchase-orders",
        headers=manager.headers,
        json={"supplier_id": supplier["id"], "items": [{"ingredient_id": rice["id"], "quantity": "2", "unit": "kg"}]},
    ).json()
    client.post(f"/api/v1/purchase-orders/{po['id']}/submit", headers=manager.headers)
    start = _cursor(client, manager)
    received = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        headers={**manager.headers, "Idempotency-Key": "rt-receive-1"},
        json={"lines": [{"item_id": po["items"][0]["id"], "quantity": "1", "unit": "kg"}]},
    )
    assert received.status_code == 200, received.text
    types = [e["type"] for e in _events(client, manager, start)]
    assert {"po.received", "stock.changed", "notification.created"} <= set(types)
    note = client.get("/api/v1/notifications", headers=manager.headers).json()["items"][0]
    assert note["kind"] == "PO_RECEIVED" and note["title"].endswith("partly received")
    assert note["link"] == f"/purchase-orders/{po['id']}"


def test_stream_delivers_events_as_server_sent_events(client: TestClient, factory: Factory, monkeypatch) -> None:
    rid, manager, cashier, _, _, dish = _setup(factory)
    settings = get_settings()
    monkeypatch.setattr(settings, "events_stream_seconds", 1)
    monkeypatch.setattr(settings, "events_poll_interval_seconds", 0.2)
    start = _cursor(client, manager)
    order = _sell(client, cashier, dish).json()

    bearer = {"Authorization": manager.headers["Authorization"]}  # the stream takes the restaurant from the query
    with client.stream(
        "GET", "/api/v1/events/stream", headers=bearer, params={"restaurant_id": str(rid), "after": start}
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert "no-transform" in response.headers["cache-control"]
        body = "".join(response.iter_text())
    frames = [f for f in body.split("\n\n") if f.strip()]
    assert frames[0].startswith("retry: 2000") and "event: ready" in frames[0]
    payloads = [
        json.loads(line[len("data: ") :]) for f in frames for line in f.split("\n") if line.startswith('data: {"')
    ]
    assert any(p["type"] == "order.confirmed" and p["entity_id"] == order["id"] for p in payloads)

    # A reconnect with Last-Event-ID resumes after the newest event, so nothing repeats.
    newest = max(p["id"] for p in payloads)
    with client.stream(
        "GET",
        "/api/v1/events/stream",
        headers={**bearer, "Last-Event-ID": str(newest)},
        params={"restaurant_id": str(rid), "after": start},
    ) as response:
        again = "".join(response.iter_text())
    assert "order.confirmed" not in again


def test_stream_requires_membership(client: TestClient, factory: Factory) -> None:
    rid, *_ = _setup(factory)
    outsider = factory.manager(factory.restaurant("Elsewhere"))
    r = client.get(
        "/api/v1/events/stream",
        headers={"Authorization": outsider.headers["Authorization"]},
        params={"restaurant_id": str(rid)},
    )
    assert r.status_code == 403
    assert client.get("/api/v1/events/stream", params={"restaurant_id": str(rid)}).status_code == 401
