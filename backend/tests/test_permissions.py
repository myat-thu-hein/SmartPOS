"""Role-based access control matrix and staff management."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import PASSWORD, Factory

M, C, K = "MANAGER", "CASHIER", "KITCHEN"

# (method, path, body, roles that are allowed)
MATRIX = [
    ("get", "/api/v1/products", None, {M, C, K}),
    (
        "post",
        "/api/v1/products",
        {"name": "X", "category_id": "00000000-0000-0000-0000-000000000000", "price_minor": 1},
        {M},
    ),
    ("post", "/api/v1/categories", {"name": "New category"}, {M}),
    ("get", "/api/v1/modifiers/groups", None, {M, C, K}),
    ("get", "/api/v1/tables", None, {M, C}),
    ("post", "/api/v1/tables", {"name": "T99"}, {M}),
    (
        "post",
        "/api/v1/orders/quote",
        {"order_type": "TAKEAWAY", "items": [{"product_id": "00000000-0000-0000-0000-000000000000", "quantity": 1}]},
        {M, C},
    ),
    ("get", "/api/v1/orders", None, {M, C}),
    ("get", "/api/v1/kitchen/orders", None, {M, C, K}),
    ("get", "/api/v1/ingredients", None, {M}),
    ("get", "/api/v1/inventory/movements", None, {M}),
    ("get", "/api/v1/recipes", None, {M}),
    ("get", "/api/v1/suppliers", None, {M}),
    ("get", "/api/v1/purchase-orders", None, {M}),
    ("get", "/api/v1/customers", None, {M, C}),
    ("post", "/api/v1/customers", {"name": "Walk-in"}, {M, C}),
    ("get", "/api/v1/analytics/summary", None, {M}),
    ("get", "/api/v1/analytics/dashboard", None, {M, C}),
    ("get", "/api/v1/reports/orders.csv", None, {M}),
    ("get", "/api/v1/forecast/runs", None, {M}),
    ("post", "/api/v1/forecast/runs", {}, {M}),
    ("get", "/api/v1/recommendations", None, {M}),
    ("get", "/api/v1/ai/status", None, {M}),
    ("get", "/api/v1/users", None, {M}),
    ("patch", "/api/v1/restaurants/current", {"receipt_footer": "Thank you"}, {M}),
    ("get", "/api/v1/restaurants/current", None, {M, C, K}),
    ("get", "/api/v1/payments/methods", None, {M, C}),
    ("get", "/api/v1/payments", None, {M}),
    ("get", "/api/v1/discounts", None, {M, C}),
    ("post", "/api/v1/discounts", {"name": "D", "kind": "PERCENT", "value": 100}, {M}),
    ("get", "/api/v1/audit-logs", None, set()),
    ("post", "/api/v1/restaurants", {"name": "New"}, set()),
    ("get", "/api/v1/users/all", None, set()),
]


@pytest.mark.parametrize("role", [M, C, K])
def test_permission_matrix(client: TestClient, factory: Factory, role: str) -> None:
    rid = factory.restaurant()
    actor = factory.user(role, rid)
    for method, path, body, allowed in MATRIX:
        kwargs = {"headers": actor.headers}
        if body is not None:
            kwargs["json"] = body
        status = getattr(client, method)(path, **kwargs).status_code
        if role in allowed:
            assert status != 403, f"{role} should be allowed: {method.upper()} {path} -> {status}"
        else:
            assert status == 403, f"{role} should be denied: {method.upper()} {path} -> {status}"


def test_staff_management(client: TestClient, factory: Factory) -> None:
    rid = factory.restaurant()
    manager = factory.manager(rid)
    created = client.post(
        "/api/v1/users",
        headers=manager.headers,
        json={
            "email": "New.Cashier@Example.com",
            "full_name": "New Cashier",
            "password": "Cashier-pass1",
            "role": "CASHIER",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["email"] == "new.cashier@example.com"
    weak = client.post(
        "/api/v1/users",
        headers=manager.headers,
        json={"email": "weak@example.com", "full_name": "Weak", "password": "password", "role": "KITCHEN"},
    )
    assert weak.status_code == 422
    promote = client.post(
        "/api/v1/users",
        headers=manager.headers,
        json={"email": "boss@example.com", "full_name": "Boss", "password": "Boss-pass-123", "role": "MANAGER"},
    )
    assert promote.status_code == 403
    dup = client.post(
        "/api/v1/users",
        headers=manager.headers,
        json={"email": "new.cashier@example.com", "full_name": "Dup", "password": "Cashier-pass1", "role": "CASHIER"},
    )
    assert dup.status_code == 409

    user_id = created.json()["user_id"]
    login = client.post("/api/v1/auth/token", json={"email": "new.cashier@example.com", "password": "Cashier-pass1"})
    token = login.json()["access_token"]
    cashier_headers = {"Authorization": f"Bearer {token}", "X-Restaurant-ID": str(rid)}
    assert client.get("/api/v1/products", headers=cashier_headers).status_code == 200
    assert (
        client.patch(f"/api/v1/users/{user_id}", headers=manager.headers, json={"role": "MANAGER"}).status_code == 403
    )
    deactivated = client.patch(f"/api/v1/users/{user_id}", headers=manager.headers, json={"is_active": False})
    assert deactivated.json()["membership_active"] is False
    assert client.get("/api/v1/auth/me", headers=cashier_headers).status_code == 401  # sessions revoked
    assert (
        client.patch(f"/api/v1/users/{manager.user_id}", headers=manager.headers, json={"is_active": False}).status_code
        == 403
    )
    staff = client.get("/api/v1/users", headers=manager.headers).json()
    assert {s["role"] for s in staff} == {"MANAGER", "CASHIER"}


def test_admin_manages_restaurants_and_members(client: TestClient, factory: Factory) -> None:
    admin = factory.admin()
    owner = factory.user(None, None, email="owner@example.com")
    r = client.post(
        "/api/v1/restaurants", headers=admin.headers, json={"name": "New Branch", "manager_email": "owner@example.com"}
    )
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    login = client.post("/api/v1/auth/login", json={"email": owner.email, "password": PASSWORD}).json()
    assert login["memberships"][0]["role"] == "MANAGER"
    methods = client.get("/api/v1/payments/methods", headers=owner.for_restaurant(rid)).json()
    assert {m["code"] for m in methods} == {"CASH", "CARD", "QR"}
    added = client.post(
        f"/api/v1/restaurants/{rid}/members",
        headers=admin.headers,
        json={"email": "owner@example.com", "role": "CASHIER"},
    )
    assert added.status_code == 409
    platform = client.get("/api/v1/users/all", headers=admin.headers).json()
    assert platform["total"] == 2
    audit = client.get("/api/v1/audit-logs", headers=admin.headers, params={"action": "restaurant."}).json()
    assert audit["items"][0]["action"] == "restaurant.created"
    assert (
        client.patch(
            f"/api/v1/users/{admin.user_id}/platform", headers=admin.headers, json={"is_platform_admin": False}
        ).status_code
        == 403
    )
