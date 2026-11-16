"""A user of one restaurant can never read or modify another restaurant's data."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import Factory


@pytest.fixture
def two_tenants(client: TestClient, factory: Factory):
    rid_a, rid_b = factory.restaurant("Tenant A"), factory.restaurant("Tenant B")
    manager_a, manager_b = factory.manager(rid_a), factory.manager(rid_b)
    # Restaurant B data.
    cat = factory.category(manager_b, "B food")
    product = factory.product(manager_b, cat["id"], "B noodles", 9000)
    ingredient = factory.ingredient(manager_b, "B rice", "g", stock=1000)
    table = factory.table(manager_b, "B1")
    customer = client.post("/api/v1/customers", headers=manager_b.headers, json={"name": "B customer"}).json()
    supplier = client.post("/api/v1/suppliers", headers=manager_b.headers, json={"name": "B supplier"}).json()
    po = client.post(
        "/api/v1/purchase-orders",
        headers=manager_b.headers,
        json={"supplier_id": supplier["id"], "items": [{"ingredient_id": ingredient["id"], "quantity": "10"}]},
    ).json()
    order = client.post(
        "/api/v1/orders",
        headers=manager_b.headers,
        json={"order_type": "TAKEAWAY", "items": [{"product_id": product["id"], "quantity": 1}], "confirm": True},
    ).json()
    return {
        "rid_a": rid_a,
        "rid_b": rid_b,
        "a": manager_a,
        "b": manager_b,
        "product": product,
        "category": cat,
        "ingredient": ingredient,
        "table": table,
        "customer": customer,
        "supplier": supplier,
        "po": po,
        "order": order,
    }


def test_header_spoofing_is_refused(client: TestClient, two_tenants) -> None:
    a, rid_b = two_tenants["a"], two_tenants["rid_b"]
    for path in (
        "/api/v1/products",
        "/api/v1/orders",
        "/api/v1/ingredients",
        "/api/v1/customers",
        "/api/v1/analytics/summary",
        "/api/v1/restaurants/current",
        "/api/v1/users",
    ):
        r = client.get(path, headers=a.for_restaurant(rid_b))
        assert r.status_code == 403, path
        assert r.json()["error"]["code"] == "restaurant_forbidden"
    bogus = client.get("/api/v1/products", headers={**a.headers, "X-Restaurant-ID": "not-a-uuid"})
    assert bogus.status_code == 422


def test_cross_tenant_ids_are_not_found(client: TestClient, two_tenants) -> None:
    t = two_tenants
    h = t["a"].headers
    reads = [
        f"/api/v1/products/{t['product']['id']}",
        f"/api/v1/ingredients/{t['ingredient']['id']}",
        f"/api/v1/tables/{t['table']['id']}",
        f"/api/v1/customers/{t['customer']['id']}",
        f"/api/v1/suppliers/{t['supplier']['id']}",
        f"/api/v1/purchase-orders/{t['po']['id']}",
        f"/api/v1/orders/{t['order']['id']}",
        f"/api/v1/orders/{t['order']['id']}/receipt",
        f"/api/v1/recipes/products/{t['product']['id']}",
    ]
    for path in reads:
        assert client.get(path, headers=h).status_code == 404, path

    writes = [
        ("patch", f"/api/v1/products/{t['product']['id']}", {"price_minor": 1}),
        ("patch", f"/api/v1/categories/{t['category']['id']}", {"name": "hacked"}),
        ("patch", f"/api/v1/ingredients/{t['ingredient']['id']}", {"name": "hacked"}),
        (
            "post",
            "/api/v1/inventory/movements",
            {"ingredient_id": t["ingredient"]["id"], "movement_type": "WASTE", "quantity": "100", "reason": "sabotage"},
        ),
        ("patch", f"/api/v1/customers/{t['customer']['id']}", {"name": "hacked"}),
        ("post", f"/api/v1/orders/{t['order']['id']}/cancel", {"reason": "sabotage"}),
        ("post", f"/api/v1/orders/{t['order']['id']}/status", {"status": "PREPARING"}),
        ("post", f"/api/v1/purchase-orders/{t['po']['id']}/submit", None),
        ("post", f"/api/v1/tables/{t['table']['id']}/status", {"status": "RESERVED"}),
        (
            "put",
            f"/api/v1/recipes/products/{t['product']['id']}",
            {"items": [{"ingredient_id": t["ingredient"]["id"], "quantity": "1"}]},
        ),
    ]
    for method, path, body in writes:
        r = (
            getattr(client, method)(path, headers=h, json=body)
            if body is not None
            else getattr(client, method)(path, headers=h)
        )
        assert r.status_code == 404, (method, path, r.text)

    # Restaurant A cannot use B's product, table or customer in its own order.
    r = client.post(
        "/api/v1/orders",
        headers=h,
        json={"order_type": "TAKEAWAY", "items": [{"product_id": t["product"]["id"], "quantity": 1}]},
    )
    assert r.status_code == 422
    own_cat = client.post("/api/v1/categories", headers=h, json={"name": "A food"}).json()
    own = client.post(
        "/api/v1/products", headers=h, json={"name": "A rice", "category_id": own_cat["id"], "price_minor": 100}
    ).json()
    r = client.post(
        "/api/v1/orders",
        headers=h,
        json={
            "order_type": "DINE_IN",
            "table_id": t["table"]["id"],
            "items": [{"product_id": own["id"], "quantity": 1}],
        },
    )
    assert r.status_code == 404
    r = client.post(
        "/api/v1/orders",
        headers=h,
        json={
            "order_type": "TAKEAWAY",
            "customer_id": t["customer"]["id"],
            "items": [{"product_id": own["id"], "quantity": 1}],
        },
    )
    assert r.status_code == 404
    # Nothing in B changed.
    b = t["b"].headers
    assert client.get(f"/api/v1/products/{t['product']['id']}", headers=b).json()["price_minor"] == 9000
    assert client.get(f"/api/v1/ingredients/{t['ingredient']['id']}", headers=b).json()["current_stock"] == 1000.0
    assert client.get(f"/api/v1/orders/{t['order']['id']}", headers=b).json()["status"] == "CONFIRMED"


def test_lists_only_show_own_data(client: TestClient, two_tenants) -> None:
    h = two_tenants["a"].headers
    assert client.get("/api/v1/products", headers=h).json() == []
    assert client.get("/api/v1/suppliers", headers=h).json() == []
    assert client.get("/api/v1/orders", headers=h).json()["total"] == 0
    assert client.get("/api/v1/customers", headers=h).json()["total"] == 0
    assert client.get("/api/v1/inventory/movements", headers=h).json()["total"] == 0
    assert client.get("/api/v1/kitchen/orders", headers=h).json() == []
    assert client.get("/api/v1/analytics/dashboard", headers=h).json()["recent_orders"] == []
    restaurants = client.get("/api/v1/restaurants", headers=h).json()
    assert [r["name"] for r in restaurants] == ["Tenant A"]


def test_platform_admin_and_staff_boundaries(client: TestClient, factory: Factory, two_tenants) -> None:
    admin = factory.admin()
    assert client.get("/api/v1/products", headers=admin.for_restaurant(two_tenants["rid_b"])).status_code == 200
    assert client.get("/api/v1/audit-logs", headers=admin.headers).status_code == 200
    assert client.get("/api/v1/audit-logs", headers=two_tenants["a"].headers).status_code == 403
    staff_b = client.get("/api/v1/users", headers=two_tenants["b"].headers).json()
    target = staff_b[0]["user_id"]
    r = client.patch(f"/api/v1/users/{target}", headers=two_tenants["a"].headers, json={"is_active": False})
    assert r.status_code == 404
