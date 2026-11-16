"""Menu catalog: categories, products, modifiers, tables and recipes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import Factory


def test_category_and_product_crud(client: TestClient, factory: Factory) -> None:
    rid = factory.restaurant()
    manager = factory.manager(rid)
    category = factory.category(manager, "Noodles")
    duplicate = client.post("/api/v1/categories", json={"name": "noodles"}, headers=manager.headers)
    assert duplicate.status_code == 409
    product = factory.product(
        manager, category["id"], "Pad Thai", 12000, sku="PT-01", description="Stir-fried rice noodles"
    )
    assert product["price_minor"] == 12000 and product["category_name"] == "Noodles"
    assert product["has_recipe"] is False
    sku_clash = client.post(
        "/api/v1/products",
        headers=manager.headers,
        json={"name": "Other", "category_id": category["id"], "price_minor": 100, "sku": "PT-01"},
    )
    assert sku_clash.status_code == 409
    negative = client.post(
        "/api/v1/products",
        headers=manager.headers,
        json={"name": "Bad", "category_id": category["id"], "price_minor": -1},
    )
    assert negative.status_code == 422

    updated = client.patch(
        f"/api/v1/products/{product['id']}", headers=manager.headers, json={"price_minor": 13500, "is_available": False}
    )
    assert updated.status_code == 200
    assert updated.json()["price_minor"] == 13500 and updated.json()["is_available"] is False

    listed = client.get("/api/v1/products", params={"available_only": True}, headers=manager.headers).json()
    assert listed == []
    searched = client.get("/api/v1/products", params={"search": "pad"}, headers=manager.headers).json()
    assert [p["name"] for p in searched] == ["Pad Thai"]

    cats = client.get("/api/v1/categories", headers=manager.headers).json()
    assert cats[0]["product_count"] == 1
    not_empty = client.delete(f"/api/v1/categories/{category['id']}", headers=manager.headers)
    assert not_empty.status_code == 409

    # A never-sold product is deleted outright.
    deleted = client.delete(f"/api/v1/products/{product['id']}", headers=manager.headers)
    assert deleted.json()["message"] == "Product deleted."
    assert client.delete(f"/api/v1/categories/{category['id']}", headers=manager.headers).status_code == 204


def test_product_requires_category_from_same_restaurant(client: TestClient, factory: Factory) -> None:
    rid_a, rid_b = factory.restaurant("A"), factory.restaurant("B")
    manager_a, manager_b = factory.manager(rid_a), factory.manager(rid_b)
    category_b = factory.category(manager_b, "B mains")
    r = client.post(
        "/api/v1/products",
        headers=manager_a.headers,
        json={"name": "Sneaky", "category_id": category_b["id"], "price_minor": 100},
    )
    assert r.status_code == 404


def test_modifier_groups_and_options(client: TestClient, factory: Factory) -> None:
    rid = factory.restaurant()
    manager = factory.manager(rid)
    egg = factory.ingredient(manager, "Egg", "piece", stock=30)
    group = client.post(
        "/api/v1/modifiers/groups",
        headers=manager.headers,
        json={
            "name": "Extras",
            "selection_type": "MULTIPLE",
            "min_select": 0,
            "max_select": 3,
            "options": [
                {
                    "name": "Extra egg",
                    "price_delta_minor": 1000,
                    "ingredient_id": egg["id"],
                    "ingredient_quantity": "1",
                },
                {"name": "Extra cheese", "price_delta_minor": 1500},
            ],
        },
    )
    assert group.status_code == 201, group.text
    body = group.json()
    assert [o["name"] for o in body["options"]] == ["Extra egg", "Extra cheese"]
    assert body["options"][0]["ingredient_quantity"] == 1.0

    bad_single = client.post(
        "/api/v1/modifiers/groups",
        headers=manager.headers,
        json={"name": "Size", "selection_type": "SINGLE", "min_select": 2},
    )
    assert bad_single.status_code == 422
    bad_unit = client.post(
        f"/api/v1/modifiers/groups/{body['id']}/options",
        headers=manager.headers,
        json={"name": "Egg kg", "ingredient_id": egg["id"], "ingredient_quantity": "1", "ingredient_unit": "kg"},
    )
    assert bad_unit.status_code == 422
    assert bad_unit.json()["error"]["code"] == "incompatible_unit"

    size = client.post(
        "/api/v1/modifiers/groups",
        headers=manager.headers,
        json={
            "name": "Size",
            "selection_type": "SINGLE",
            "min_select": 1,
            "options": [{"name": "Regular", "is_default": True}, {"name": "Large", "price_delta_minor": 2000}],
        },
    )
    assert size.status_code == 201
    assert size.json()["max_select"] == 1

    category = factory.category(manager)
    product = factory.product(manager, category["id"], modifier_group_ids=[size.json()["id"], body["id"]])
    assert [g["name"] for g in product["modifier_groups"]] == ["Size", "Extras"]

    option_id = body["options"][1]["id"]
    deactivated = client.patch(
        f"/api/v1/modifiers/options/{option_id}", headers=manager.headers, json={"is_active": False}
    )
    assert deactivated.status_code == 200 and deactivated.json()["is_active"] is False


def test_tables_lifecycle(client: TestClient, factory: Factory) -> None:
    rid = factory.restaurant()
    manager, cashier = factory.manager(rid), factory.cashier(rid)
    table = factory.table(manager, "T1", 4)
    assert table["status"] == "AVAILABLE"
    assert client.post("/api/v1/tables", headers=manager.headers, json={"name": "t1"}).status_code == 409
    assert client.post("/api/v1/tables", headers=cashier.headers, json={"name": "T9"}).status_code == 403
    reserved = client.post(f"/api/v1/tables/{table['id']}/status", headers=cashier.headers, json={"status": "RESERVED"})
    assert reserved.json()["status"] == "RESERVED"
    occupied = client.post(f"/api/v1/tables/{table['id']}/status", headers=cashier.headers, json={"status": "OCCUPIED"})
    assert occupied.status_code == 422
    not_occupied = client.post(f"/api/v1/tables/{table['id']}/close", headers=cashier.headers)
    assert not_occupied.status_code == 409
    assert len(client.get("/api/v1/tables", headers=cashier.headers).json()) == 1


def test_recipe_versions_and_costing(client: TestClient, factory: Factory) -> None:
    rid = factory.restaurant()
    manager = factory.manager(rid)
    noodles = factory.ingredient(manager, "Rice noodles", "g", stock=5000, opening_unit_cost_minor="0.8")
    egg = factory.ingredient(manager, "Egg", "piece", stock=30, opening_unit_cost_minor="500")
    sauce = factory.ingredient(manager, "Pad Thai sauce", "ml", stock=2000, opening_unit_cost_minor="1.5")
    category = factory.category(manager)
    product = factory.product(manager, category["id"], "Pad Thai", 12000)
    # No recipe yet is a normal state: 200 with null, not an error.
    none_yet = client.get(f"/api/v1/recipes/products/{product['id']}", headers=manager.headers)
    assert none_yet.status_code == 200 and none_yet.json() is None
    recipe = factory.recipe(
        manager,
        product["id"],
        [
            {"ingredient_id": noodles["id"], "quantity": "0.1", "unit": "kg"},
            {"ingredient_id": egg["id"], "quantity": "1"},
            {"ingredient_id": sauce["id"], "quantity": "30", "unit": "ml", "waste_factor": "0.1"},
        ],
    )
    assert recipe["version"] == 1
    by_name = {i["ingredient_name"]: i for i in recipe["items"]}
    assert by_name["Rice noodles"]["quantity"] == 100.0
    assert by_name["Rice noodles"]["input_unit"] == "kg"
    assert by_name["Pad Thai sauce"]["effective_quantity"] == 33.0
    # 100 g * 0.8 + 1 * 500 + 33 ml * 1.5 = 80 + 500 + 49.5
    assert recipe["estimated_cost_minor"] == 629.5
    assert recipe["estimated_margin_bps"] == round((12000 - 629.5) / 12000 * 10000)

    same = factory.recipe(
        manager,
        product["id"],
        [
            {"ingredient_id": noodles["id"], "quantity": "100", "unit": "g"},
            {"ingredient_id": egg["id"], "quantity": "1"},
            {"ingredient_id": sauce["id"], "quantity": "30", "waste_factor": "0.1"},
        ],
    )
    assert same["version"] == 1, "identical recipe should not create a new version"
    changed = factory.recipe(manager, product["id"], [{"ingredient_id": noodles["id"], "quantity": "120"}])
    assert changed["version"] == 2
    versions = client.get(f"/api/v1/recipes/products/{product['id']}/versions", headers=manager.headers).json()
    assert [v["version"] for v in versions] == [2, 1]
    assert [v["is_active"] for v in versions] == [True, False]

    incompatible = client.put(
        f"/api/v1/recipes/products/{product['id']}",
        headers=manager.headers,
        json={"items": [{"ingredient_id": egg["id"], "quantity": "1", "unit": "kg"}]},
    )
    assert incompatible.status_code == 422
    duplicate = client.put(
        f"/api/v1/recipes/products/{product['id']}",
        headers=manager.headers,
        json={"items": [{"ingredient_id": egg["id"], "quantity": "1"}, {"ingredient_id": egg["id"], "quantity": "2"}]},
    )
    assert duplicate.status_code == 422
    summary = client.get("/api/v1/recipes", headers=manager.headers).json()
    assert summary[0]["version"] == 2 and summary[0]["ingredient_count"] == 1
    assert client.get("/api/v1/products", headers=manager.headers).json()[0]["has_recipe"] is True


def test_ingredient_pack_units(client: TestClient, factory: Factory) -> None:
    rid = factory.restaurant()
    manager = factory.manager(rid)
    egg = factory.ingredient(manager, "Egg", "piece", units=[{"unit_name": "tray", "factor_to_base": "30"}])
    assert "tray" in egg["allowed_units"]
    receipt = client.post(
        "/api/v1/inventory/movements",
        headers=manager.headers,
        json={
            "ingredient_id": egg["id"],
            "movement_type": "RECEIPT",
            "quantity": "2",
            "unit": "tray",
            "unit_cost_minor": "12000",
            "reason": "Market purchase",
        },
    )
    assert receipt.status_code == 201, receipt.text
    assert receipt.json()["quantity"] == 60.0
    assert receipt.json()["unit_cost_minor"] == 400.0  # 120 THB per tray of 30 = 4 THB per egg
    redefine = client.post(
        f"/api/v1/ingredients/{egg['id']}/units",
        headers=manager.headers,
        json={"unit_name": "kg", "factor_to_base": "10"},
    )
    assert redefine.status_code == 422
