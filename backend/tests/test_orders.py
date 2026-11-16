"""Orders, stock deduction, payments, refunds, receipts and the kitchen display."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Ingredient, InventoryMovement
from tests.conftest import Actor, Factory


@dataclass
class Pos:
    rid: uuid.UUID
    manager: Actor
    cashier: Actor
    kitchen: Actor
    product: dict
    drink: dict
    table: dict
    noodles: dict
    egg: dict
    cash: str
    card: str


@pytest.fixture
def pos(client: TestClient, factory: Factory) -> Pos:
    # Exclusive VAT 7% and 10% service charge on dine-in, as in many Thai restaurants.
    rid = factory.restaurant("Baan Thai", prices_include_tax=False, tax_rate_bps=700, service_charge_bps=1000)
    manager = factory.manager(rid)
    noodles = factory.ingredient(manager, "Rice noodles", "g", stock=1000, opening_unit_cost_minor="0.8")
    egg = factory.ingredient(manager, "Egg", "piece", stock=10, opening_unit_cost_minor="500")
    category = factory.category(manager, "Noodles")
    product = factory.product(manager, category["id"], "Pad Thai", 12000)
    factory.recipe(
        manager,
        product["id"],
        [
            {"ingredient_id": noodles["id"], "quantity": "100", "unit": "g"},
            {"ingredient_id": egg["id"], "quantity": "1"},
        ],
    )
    drinks = factory.category(manager, "Drinks")
    drink = factory.product(manager, drinks["id"], "Thai iced tea", 5000)
    table = factory.table(manager, "T1")
    return Pos(
        rid=rid,
        manager=manager,
        cashier=factory.cashier(rid),
        kitchen=factory.kitchen(rid),
        product=product,
        drink=drink,
        table=table,
        noodles=noodles,
        egg=egg,
        cash=factory.payment_method_id(manager, "CASH"),
        card=factory.payment_method_id(manager, "CARD"),
    )


def stock(db, ingredient_id: str) -> Decimal:
    db.expire_all()
    return db.get(Ingredient, uuid.UUID(ingredient_id)).current_stock


def create(
    client: TestClient,
    actor: Actor,
    items: list[dict],
    *,
    order_type: str = "TAKEAWAY",
    table_id: str | None = None,
    confirm: bool = False,
    key: str | None = None,
    **extra,
) -> dict:
    headers = dict(actor.headers)
    if key:
        headers["Idempotency-Key"] = key
    payload = {"order_type": order_type, "items": items, "confirm": confirm, **extra}
    if table_id:
        payload["table_id"] = table_id
    r = client.post("/api/v1/orders", json=payload, headers=headers)
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_quote_and_server_side_totals(client: TestClient, pos: Pos) -> None:
    r = client.post(
        "/api/v1/orders/quote",
        headers=pos.cashier.headers,
        json={
            "order_type": "DINE_IN",
            "table_id": pos.table["id"],
            "items": [{"product_id": pos.product["id"], "quantity": 2}, {"product_id": pos.drink["id"], "quantity": 1}],
        },
    )
    assert r.status_code == 200, r.text
    q = r.json()
    assert q["subtotal_minor"] == 29000
    assert q["service_charge_minor"] == 2900
    assert q["tax_minor"] == 2233  # 7% of 319.00
    assert q["total_minor"] == 29000 + 2900 + 2233
    # Takeaway: no service charge when configured dine-in only.
    takeaway = client.post(
        "/api/v1/orders/quote",
        headers=pos.cashier.headers,
        json={"order_type": "TAKEAWAY", "items": [{"product_id": pos.product["id"], "quantity": 1}]},
    ).json()
    assert takeaway["service_charge_minor"] == 0 and takeaway["total_minor"] == 12840


def test_client_cannot_override_prices(client: TestClient, pos: Pos) -> None:
    # Price fields are not part of the request schema: they are rejected, never trusted.
    for payload in (
        {"items": [{"product_id": pos.product["id"], "quantity": 1, "unit_price_minor": 1}]},
        {"items": [{"product_id": pos.product["id"], "quantity": 1}], "total_minor": 1},
    ):
        r = client.post("/api/v1/orders", headers=pos.cashier.headers, json={"order_type": "TAKEAWAY", **payload})
        assert r.status_code == 422
        assert r.json()["error"]["details"][0]["type"] == "extra_forbidden"
    order = create(client, pos.cashier, [{"product_id": pos.product["id"], "quantity": 1}])
    assert order["items"][0]["unit_price_minor"] == 12000
    assert order["total_minor"] == 12840


def test_full_order_lifecycle_with_stock_and_kitchen(client: TestClient, pos: Pos, db) -> None:
    order = create(
        client,
        pos.cashier,
        [{"product_id": pos.product["id"], "quantity": 2, "notes": "no peanuts"}],
        order_type="DINE_IN",
        table_id=pos.table["id"],
    )
    assert order["status"] == "DRAFT" and order["stock_committed"] is False
    assert stock(db, pos.noodles["id"]) == Decimal(1000)
    table = client.get(f"/api/v1/tables/{pos.table['id']}", headers=pos.cashier.headers).json()
    assert table["status"] == "OCCUPIED" and table["current_order"]["id"] == order["id"]

    confirmed = client.post(f"/api/v1/orders/{order['id']}/confirm", headers=pos.cashier.headers).json()
    assert confirmed["status"] == "CONFIRMED" and confirmed["stock_committed"] is True
    assert stock(db, pos.noodles["id"]) == Decimal(800)
    assert stock(db, pos.egg["id"]) == Decimal(8)
    # Confirming again does not deduct twice.
    again = client.post(f"/api/v1/orders/{order['id']}/confirm", headers=pos.cashier.headers)
    assert again.status_code == 200
    assert stock(db, pos.noodles["id"]) == Decimal(800)
    movements = db.scalars(select(InventoryMovement).where(InventoryMovement.order_id == uuid.UUID(order["id"]))).all()
    assert {m.movement_type.value for m in movements} == {"SALE"}
    assert all(m.actor_user_id == pos.cashier.user_id for m in movements)

    tickets = client.get("/api/v1/kitchen/orders", headers=pos.kitchen.headers).json()
    assert [t["kitchen_status"] for t in tickets] == ["NEW"]
    assert tickets[0]["label"] == "Table T1"
    assert tickets[0]["items"][0]["notes"] == "no peanuts"
    assert "total_minor" not in tickets[0]
    # Kitchen cannot skip steps; cashiers cannot drive kitchen statuses.
    skip = client.post(
        f"/api/v1/kitchen/orders/{order['id']}/status", headers=pos.kitchen.headers, json={"status": "READY"}
    )
    assert skip.status_code == 409
    forbidden = client.post(
        f"/api/v1/kitchen/orders/{order['id']}/status", headers=pos.cashier.headers, json={"status": "PREPARING"}
    )
    assert forbidden.status_code == 403
    for step in ("PREPARING", "READY"):
        r = client.post(
            f"/api/v1/kitchen/orders/{order['id']}/status", headers=pos.kitchen.headers, json={"status": step}
        )
        assert r.status_code == 200 and r.json()["kitchen_status"] == step

    total = confirmed["total_minor"]
    pay = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=pos.cashier.headers,
        json={"payment_method_id": pos.cash, "amount_minor": total, "amount_tendered_minor": 30000},
    )
    assert pay.status_code == 201, pay.text
    paid = pay.json()
    assert paid["payment_status"] == "PAID"
    assert paid["payments"][0]["change_minor"] == 30000 - total
    assert paid["payments"][0]["is_simulated"] is True

    done = client.post(
        f"/api/v1/kitchen/orders/{order['id']}/status", headers=pos.kitchen.headers, json={"status": "COMPLETED"}
    )
    assert done.json()["kitchen_status"] == "COMPLETED"
    closed = client.post(f"/api/v1/tables/{pos.table['id']}/close", headers=pos.cashier.headers)
    assert closed.status_code == 200 and closed.json()["status"] == "CLEANING"
    available = client.post(
        f"/api/v1/tables/{pos.table['id']}/status", headers=pos.cashier.headers, json={"status": "AVAILABLE"}
    )
    assert available.json()["status"] == "AVAILABLE"

    receipt = client.get(f"/api/v1/orders/{order['id']}/receipt", headers=pos.cashier.headers).json()
    assert receipt["restaurant_name"] == "Baan Thai"
    assert receipt["total_minor"] == total and receipt["payment_status"] == "PAID"
    assert receipt["lines"][0]["quantity"] == 2
    assert receipt["simulated_payment_notice"]
    assert receipt["payments"][0]["method_name"].endswith("(simulated)")


def test_table_conflicts(client: TestClient, pos: Pos) -> None:
    create(
        client,
        pos.cashier,
        [{"product_id": pos.drink["id"], "quantity": 1}],
        order_type="DINE_IN",
        table_id=pos.table["id"],
    )
    r = client.post(
        "/api/v1/orders",
        headers=pos.cashier.headers,
        json={
            "order_type": "DINE_IN",
            "table_id": pos.table["id"],
            "items": [{"product_id": pos.drink["id"], "quantity": 1}],
        },
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "table_has_active_order"
    close = client.post(f"/api/v1/tables/{pos.table['id']}/close", headers=pos.cashier.headers)
    assert close.status_code == 409 and close.json()["error"]["code"] == "table_has_open_orders"
    missing_table = client.post(
        "/api/v1/orders",
        headers=pos.cashier.headers,
        json={"order_type": "DINE_IN", "items": [{"product_id": pos.drink["id"], "quantity": 1}]},
    )
    assert missing_table.status_code == 422


def test_insufficient_stock_blocks_confirmation_atomically(client: TestClient, pos: Pos, db) -> None:
    order = create(client, pos.cashier, [{"product_id": pos.product["id"], "quantity": 11}])
    r = client.post(f"/api/v1/orders/{order['id']}/confirm", headers=pos.cashier.headers)
    assert r.status_code == 409
    error = r.json()["error"]
    assert error["code"] == "insufficient_stock"
    names = {s["ingredient_name"] for s in error["details"]["shortages"]}
    assert names == {"Rice noodles", "Egg"}
    assert stock(db, pos.noodles["id"]) == Decimal(1000) and stock(db, pos.egg["id"]) == Decimal(10)
    detail = client.get(f"/api/v1/orders/{order['id']}", headers=pos.cashier.headers).json()
    assert detail["status"] == "DRAFT"


def test_negative_stock_only_when_manager_enables_it(client: TestClient, pos: Pos, db) -> None:
    denied = client.patch(
        "/api/v1/restaurants/current", headers=pos.cashier.headers, json={"allow_negative_stock": True}
    )
    assert denied.status_code == 403
    assert (
        client.patch(
            "/api/v1/restaurants/current", headers=pos.manager.headers, json={"allow_negative_stock": True}
        ).status_code
        == 200
    )
    create(client, pos.cashier, [{"product_id": pos.product["id"], "quantity": 11}], confirm=True)
    assert stock(db, pos.egg["id"]) == Decimal(-1)


def test_cancellation_restores_stock_only_before_preparation(client: TestClient, pos: Pos, db) -> None:
    order = create(client, pos.cashier, [{"product_id": pos.product["id"], "quantity": 3}], confirm=True)
    assert stock(db, pos.egg["id"]) == Decimal(7)
    # Cashiers may only cancel drafts.
    denied = client.post(
        f"/api/v1/orders/{order['id']}/cancel", headers=pos.cashier.headers, json={"reason": "customer left"}
    )
    assert denied.status_code == 403
    r = client.post(
        f"/api/v1/orders/{order['id']}/cancel", headers=pos.manager.headers, json={"reason": "customer left"}
    )
    assert r.status_code == 200 and r.json()["stock_restored"] is True
    assert stock(db, pos.egg["id"]) == Decimal(10)
    # Cancelling twice is a no-op, not a second restoration.
    assert (
        client.post(
            f"/api/v1/orders/{order['id']}/cancel", headers=pos.manager.headers, json={"reason": "again"}
        ).json()["stock_restored"]
        is False
    )
    assert stock(db, pos.egg["id"]) == Decimal(10)

    cooking = create(client, pos.cashier, [{"product_id": pos.product["id"], "quantity": 2}], confirm=True)
    client.post(
        f"/api/v1/kitchen/orders/{cooking['id']}/status", headers=pos.kitchen.headers, json={"status": "PREPARING"}
    )
    r = client.post(f"/api/v1/orders/{cooking['id']}/cancel", headers=pos.manager.headers, json={"reason": "burnt"})
    assert r.json()["stock_restored"] is False
    assert stock(db, pos.egg["id"]) == Decimal(8)

    draft = create(client, pos.cashier, [{"product_id": pos.product["id"], "quantity": 1}])
    ok = client.post(f"/api/v1/orders/{draft['id']}/cancel", headers=pos.cashier.headers, json={"reason": "mistake"})
    assert ok.status_code == 200 and ok.json()["order"]["status"] == "CANCELLED"


def test_modifying_confirmed_order_reconciles_stock(client: TestClient, pos: Pos, db) -> None:
    order = create(client, pos.cashier, [{"product_id": pos.product["id"], "quantity": 2}], confirm=True)
    assert stock(db, pos.egg["id"]) == Decimal(8)
    more = client.patch(
        f"/api/v1/orders/{order['id']}",
        headers=pos.cashier.headers,
        json={
            "items": [{"product_id": pos.product["id"], "quantity": 3}, {"product_id": pos.drink["id"], "quantity": 1}]
        },
    )
    assert more.status_code == 200, more.text
    assert stock(db, pos.egg["id"]) == Decimal(7)
    assert stock(db, pos.noodles["id"]) == Decimal(700)
    fewer = client.patch(
        f"/api/v1/orders/{order['id']}",
        headers=pos.cashier.headers,
        json={"items": [{"product_id": pos.product["id"], "quantity": 1}]},
    )
    assert fewer.status_code == 200
    assert stock(db, pos.egg["id"]) == Decimal(9)
    types = [
        m.movement_type.value
        for m in db.scalars(
            select(InventoryMovement)
            .where(
                InventoryMovement.order_id == uuid.UUID(order["id"]),
                InventoryMovement.ingredient_id == uuid.UUID(pos.egg["id"]),
            )
            .order_by(InventoryMovement.created_at)
        ).all()
    ]
    assert types == ["SALE", "SALE", "SALE_REVERSAL"]
    # Stock for this order equals exactly one serving.
    assert fewer.json()["total_minor"] == 12840


def test_recipe_change_does_not_alter_existing_order_consumption(client: TestClient, pos: Pos, db) -> None:
    order = create(client, pos.cashier, [{"product_id": pos.product["id"], "quantity": 1}], confirm=True)
    pos_recipe = client.put(
        f"/api/v1/recipes/products/{pos.product['id']}",
        headers=pos.manager.headers,
        json={"items": [{"ingredient_id": pos.egg["id"], "quantity": "2"}]},
    )
    assert pos_recipe.json()["version"] == 2
    # Editing notes only does not touch stock even though the recipe changed.
    client.patch(f"/api/v1/orders/{order['id']}", headers=pos.cashier.headers, json={"notes": "extra spicy"})
    assert stock(db, pos.egg["id"]) == Decimal(9)
    assert stock(db, pos.noodles["id"]) == Decimal(900)
    new = create(client, pos.cashier, [{"product_id": pos.product["id"], "quantity": 1}], confirm=True)
    assert stock(db, pos.egg["id"]) == Decimal(7)
    assert new["items"][0]["recipe_id"] != order["items"][0]["recipe_id"]


def test_modifier_pricing_and_ingredient_consumption(client: TestClient, pos: Pos, db) -> None:
    group = client.post(
        "/api/v1/modifiers/groups",
        headers=pos.manager.headers,
        json={
            "name": "Extras",
            "selection_type": "MULTIPLE",
            "max_select": 2,
            "options": [
                {
                    "name": "Extra egg",
                    "price_delta_minor": 1000,
                    "ingredient_id": pos.egg["id"],
                    "ingredient_quantity": "1",
                }
            ],
        },
    ).json()
    size = client.post(
        "/api/v1/modifiers/groups",
        headers=pos.manager.headers,
        json={
            "name": "Size",
            "selection_type": "SINGLE",
            "min_select": 1,
            "options": [{"name": "Regular", "is_default": True}, {"name": "Large", "price_delta_minor": 3000}],
        },
    ).json()
    client.put(
        f"/api/v1/products/{pos.product['id']}/modifier-groups",
        headers=pos.manager.headers,
        json={"modifier_group_ids": [size["id"], group["id"]]},
    )
    extra_egg = group["options"][0]["id"]
    large = size["options"][1]["id"]
    order = create(
        client,
        pos.cashier,
        [{"product_id": pos.product["id"], "quantity": 2, "modifier_option_ids": [large, extra_egg]}],
        confirm=True,
    )
    item = order["items"][0]
    assert item["unit_price_minor"] == 12000 + 3000 + 1000
    assert {m["option_name"] for m in item["modifiers"]} == {"Large", "Extra egg"}
    assert stock(db, pos.egg["id"]) == Decimal(10 - 2 - 2)
    # Default option applied automatically for required single-choice groups.
    regular = create(client, pos.cashier, [{"product_id": pos.product["id"], "quantity": 1}])
    assert [m["option_name"] for m in regular["items"][0]["modifiers"]] == ["Regular"]
    two_sizes = client.post(
        "/api/v1/orders/quote",
        headers=pos.cashier.headers,
        json={
            "order_type": "TAKEAWAY",
            "items": [
                {
                    "product_id": pos.product["id"],
                    "quantity": 1,
                    "modifier_option_ids": [large, size["options"][0]["id"]],
                }
            ],
        },
    )
    assert two_sizes.status_code == 422 and two_sizes.json()["error"]["code"] == "modifier_limit"
    foreign = client.post(
        "/api/v1/orders/quote",
        headers=pos.cashier.headers,
        json={
            "order_type": "TAKEAWAY",
            "items": [{"product_id": pos.drink["id"], "quantity": 1, "modifier_option_ids": [extra_egg]}],
        },
    )
    assert foreign.status_code == 422 and foreign.json()["error"]["code"] == "invalid_modifier"


def test_unavailable_products_cannot_be_ordered(client: TestClient, pos: Pos) -> None:
    client.patch(f"/api/v1/products/{pos.drink['id']}", headers=pos.manager.headers, json={"is_available": False})
    r = client.post(
        "/api/v1/orders",
        headers=pos.cashier.headers,
        json={"order_type": "TAKEAWAY", "items": [{"product_id": pos.drink["id"], "quantity": 1}]},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "product_unavailable"


def test_discount_authorisation(client: TestClient, pos: Pos) -> None:
    small = client.post(
        "/api/v1/discounts", headers=pos.manager.headers, json={"name": "Staff 5%", "kind": "PERCENT", "value": 500}
    ).json()
    big = client.post(
        "/api/v1/discounts", headers=pos.manager.headers, json={"name": "VIP 30%", "kind": "PERCENT", "value": 3000}
    ).json()
    vip = client.post(
        "/api/v1/discounts",
        headers=pos.manager.headers,
        json={"name": "Owner", "kind": "FIXED", "value": 1000, "requires_manager": True},
    ).json()
    items = [{"product_id": pos.product["id"], "quantity": 1}]
    ok = create(client, pos.cashier, items, discount={"discount_id": small["id"]})
    assert ok["discount_minor"] == 600 and ok["discount_name"] == "Staff 5%"
    for discount in (
        {"discount_id": big["id"]},
        {"discount_id": vip["id"]},
        {"kind": "PERCENT", "value": 500, "reason": "nice"},
    ):
        r = client.post(
            "/api/v1/orders",
            headers=pos.cashier.headers,
            json={"order_type": "TAKEAWAY", "items": items, "discount": discount},
        )
        assert r.status_code == 403, discount
    managed = create(client, pos.manager, items, discount={"kind": "FIXED", "value": 2000, "reason": "complaint"})
    assert managed["discount_minor"] == 2000
    assert managed["total_minor"] == round((12000 - 2000) * 1.07)


def test_order_idempotency(client: TestClient, pos: Pos) -> None:
    items = [{"product_id": pos.drink["id"], "quantity": 1}]
    first = create(client, pos.cashier, items, key="order-key-0001", confirm=True)
    r = client.post(
        "/api/v1/orders",
        json={"order_type": "TAKEAWAY", "items": items, "confirm": True},
        headers={**pos.cashier.headers, "Idempotency-Key": "order-key-0001"},
    )
    assert r.status_code == 200 and r.headers["Idempotent-Replayed"] == "true"
    assert r.json()["id"] == first["id"]
    listed = client.get("/api/v1/orders", headers=pos.cashier.headers).json()
    assert listed["total"] == 1


def test_payment_rules_idempotency_and_partial_payments(client: TestClient, pos: Pos) -> None:
    items = [{"product_id": pos.product["id"], "quantity": 1}]
    draft = create(client, pos.cashier, items)
    not_confirmed = client.post(
        f"/api/v1/orders/{draft['id']}/payments",
        headers=pos.cashier.headers,
        json={"payment_method_id": pos.cash, "amount_minor": 100},
    )
    assert not_confirmed.status_code == 409
    order = create(client, pos.cashier, items, confirm=True)
    total = order["total_minor"]
    over = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=pos.cashier.headers,
        json={"payment_method_id": pos.card, "amount_minor": total + 1},
    )
    assert over.status_code == 422 and over.json()["error"]["code"] == "amount_exceeds_balance"
    short_cash = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=pos.cashier.headers,
        json={"payment_method_id": pos.cash, "amount_minor": 5000, "amount_tendered_minor": 4000},
    )
    assert short_cash.status_code == 422
    headers = {**pos.cashier.headers, "Idempotency-Key": "pay-key-000001"}
    first = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=headers,
        json={"payment_method_id": pos.card, "amount_minor": 5000, "reference": "slip-1"},
    )
    assert first.status_code == 201 and first.json()["payment_status"] == "PARTIALLY_PAID"
    dup = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=headers,
        json={"payment_method_id": pos.card, "amount_minor": 5000, "reference": "slip-1"},
    )
    assert dup.status_code == 200 and dup.headers["Idempotent-Replayed"] == "true"
    assert dup.json()["amount_paid_minor"] == 5000
    reused = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=headers,
        json={"payment_method_id": pos.card, "amount_minor": 1000},
    )
    assert reused.status_code == 409 and reused.json()["error"]["code"] == "idempotency_key_reused"
    rest = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=pos.cashier.headers,
        json={"payment_method_id": pos.cash, "amount_minor": total - 5000},
    )
    assert rest.json()["payment_status"] == "PAID" and rest.json()["balance_due_minor"] == 0
    after = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=pos.cashier.headers,
        json={"payment_method_id": pos.cash, "amount_minor": 1},
    )
    assert after.status_code == 409
    locked = client.patch(f"/api/v1/orders/{order['id']}", headers=pos.cashier.headers, json={"notes": "x"})
    assert locked.status_code == 409


def test_refunds(client: TestClient, pos: Pos, db) -> None:
    order = create(client, pos.cashier, [{"product_id": pos.product["id"], "quantity": 1}], confirm=True)
    paid = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=pos.cashier.headers,
        json={"payment_method_id": pos.card, "amount_minor": order["total_minor"]},
    ).json()
    payment_id = paid["payments"][0]["id"]
    denied = client.post(
        f"/api/v1/orders/{order['id']}/refunds",
        headers=pos.cashier.headers,
        json={"payment_id": payment_id, "amount_minor": 100, "reason": "cold food"},
    )
    assert denied.status_code == 403
    headers = {**pos.manager.headers, "Idempotency-Key": "refund-key-01"}
    partial = client.post(
        f"/api/v1/orders/{order['id']}/refunds",
        headers=headers,
        json={"payment_id": payment_id, "amount_minor": 2840, "reason": "cold food"},
    )
    assert partial.status_code == 201 and partial.json()["payment_status"] == "PARTIALLY_REFUNDED"
    replay = client.post(
        f"/api/v1/orders/{order['id']}/refunds",
        headers=headers,
        json={"payment_id": payment_id, "amount_minor": 2840, "reason": "cold food"},
    )
    assert replay.status_code == 200 and replay.json()["amount_refunded_minor"] == 2840
    too_much = client.post(
        f"/api/v1/orders/{order['id']}/refunds",
        headers=pos.manager.headers,
        json={"payment_id": payment_id, "amount_minor": 10001, "reason": "x" * 5},
    )
    assert too_much.status_code == 422
    full = client.post(
        f"/api/v1/orders/{order['id']}/refunds",
        headers=pos.manager.headers,
        json={"payment_id": payment_id, "amount_minor": 10000, "reason": "complaint"},
    )
    assert full.json()["payment_status"] == "REFUNDED"
    # Refunds do not put consumed food back into stock.
    assert stock(db, pos.egg["id"]) == Decimal(9)
    cancel_paid = create(client, pos.cashier, [{"product_id": pos.drink["id"], "quantity": 1}], confirm=True)
    client.post(
        f"/api/v1/orders/{cancel_paid['id']}/payments",
        headers=pos.cashier.headers,
        json={"payment_method_id": pos.cash, "amount_minor": cancel_paid["total_minor"]},
    )
    r = client.post(
        f"/api/v1/orders/{cancel_paid['id']}/cancel", headers=pos.manager.headers, json={"reason": "wrong order"}
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "order_has_payments"


def test_zero_total_order_is_marked_paid(client: TestClient, pos: Pos) -> None:
    order = create(
        client,
        pos.manager,
        [{"product_id": pos.drink["id"], "quantity": 1}],
        discount={"kind": "PERCENT", "value": 10000, "reason": "complimentary"},
        confirm=True,
    )
    assert order["total_minor"] == 0 and order["payment_status"] == "PAID"


def test_concurrent_confirmations_never_oversell(client: TestClient, factory: Factory, pos: Pos, db) -> None:
    # 10 eggs in stock; 6 orders of 2 Pad Thai each race to confirm. Only 5 can succeed.
    drafts = [create(client, pos.cashier, [{"product_id": pos.product["id"], "quantity": 2}]) for _ in range(6)]
    results: list[int] = []
    lock = threading.Lock()

    def confirm(order_id: str) -> None:
        r = client.post(f"/api/v1/orders/{order_id}/confirm", headers=pos.cashier.headers)
        with lock:
            results.append(r.status_code)

    threads = [threading.Thread(target=confirm, args=(d["id"],)) for d in drafts]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [200] * 5 + [409]
    assert stock(db, pos.egg["id"]) == Decimal(0)
    assert stock(db, pos.noodles["id"]) == Decimal(0)


def test_concurrent_duplicate_payment_requests(client: TestClient, pos: Pos) -> None:
    order = create(client, pos.cashier, [{"product_id": pos.product["id"], "quantity": 1}], confirm=True)
    statuses: list[int] = []

    def pay() -> None:
        r = client.post(
            f"/api/v1/orders/{order['id']}/payments",
            headers={**pos.cashier.headers, "Idempotency-Key": "double-click-1"},
            json={"payment_method_id": pos.cash, "amount_minor": order["total_minor"]},
        )
        statuses.append(r.status_code)

    threads = [threading.Thread(target=pay) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert statuses.count(201) == 1 and all(s in (200, 201) for s in statuses)
    detail = client.get(f"/api/v1/orders/{order['id']}", headers=pos.cashier.headers).json()
    assert detail["amount_paid_minor"] == order["total_minor"] and len(detail["payments"]) == 1


def test_ledger_is_append_only(db, client: TestClient, pos: Pos) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    create(client, pos.cashier, [{"product_id": pos.product["id"], "quantity": 1}], confirm=True)
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE inventory_movements SET quantity = 1"))
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM inventory_movements"))
    db.rollback()
