"""One-click demo sign-in for portfolio deployments."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import get_settings
from tests.conftest import PASSWORD, Factory


def _demo(factory: Factory):
    rid = factory.restaurant("Baan Demo", is_demo=True)
    return rid, factory.manager(rid), factory.cashier(rid)


def test_demo_sign_in_is_off_by_default(client: TestClient, factory: Factory, monkeypatch) -> None:
    from app.core.config import Settings

    assert Settings.model_fields["demo_login_enabled"].default is False
    monkeypatch.setattr(get_settings(), "demo_login_enabled", False)  # independent of a local .env
    _demo(factory)
    assert client.get("/api/v1/auth/demo").json() == {"enabled": False, "restaurant_name": None, "roles": []}
    r = client.post("/api/v1/auth/demo-login", json={"role": "MANAGER"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "demo_disabled"


def test_demo_sign_in_by_role(client: TestClient, factory: Factory, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "demo_login_enabled", True)
    rid, _, cashier = _demo(factory)
    factory.admin()  # administrators are never offered

    info = client.get("/api/v1/auth/demo").json()
    assert info["enabled"] is True and info["restaurant_name"] == "Baan Demo"
    assert [r["role"] for r in info["roles"]] == ["MANAGER", "CASHIER"]  # no kitchen account exists

    r = client.post("/api/v1/auth/demo-login", json={"role": "CASHIER"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == cashier.email and body["memberships"][0]["restaurant_id"] == str(rid)
    assert "password" not in r.text.lower()
    assert client.cookies.get(get_settings().session_cookie_name)  # signed in with a normal session
    me = client.get("/api/v1/auth/me").json()
    assert me["user"]["id"] == str(cashier.user_id)

    missing = client.post("/api/v1/auth/demo-login", json={"role": "KITCHEN"})
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "demo_unavailable"
    assert client.post("/api/v1/auth/demo-login", json={"role": "ADMIN"}).status_code == 422


def test_shared_demo_accounts_cannot_change_sign_in_or_staff(client: TestClient, factory: Factory, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "demo_login_enabled", True)
    _, manager, cashier = _demo(factory)

    def refused(response) -> None:
        assert response.status_code == 403 and response.json()["error"]["code"] == "demo_restricted", response.text

    h = manager.headers
    refused(
        client.post(
            "/api/v1/auth/change-password",
            headers=h,
            json={"current_password": PASSWORD, "new_password": "An0ther-pass!"},
        )
    )
    refused(client.patch("/api/v1/auth/me", headers=h, json={"full_name": "Someone else"}))
    refused(
        client.post(
            "/api/v1/users",
            headers=h,
            json={
                "email": "real.person@example.com",
                "full_name": "Real",
                "role": "CASHIER",
                "password": "Str0ng-pass-1",
            },
        )
    )
    refused(client.patch(f"/api/v1/users/{cashier.user_id}", headers=h, json={"is_active": False}))
    refused(client.post(f"/api/v1/users/{cashier.user_id}/password", headers=h, json={"new_password": "Str0ng-pass-2"}))
    # Everything else in the demo restaurant works as usual.
    assert client.post("/api/v1/categories", headers=h, json={"name": "Specials"}).status_code == 201

    # A manager of a real restaurant is not affected, even while demo sign-in is on.
    real = factory.manager(factory.restaurant("Real Thai"))
    assert client.patch("/api/v1/auth/me", headers=real.headers, json={"full_name": "Real Manager"}).status_code == 200
