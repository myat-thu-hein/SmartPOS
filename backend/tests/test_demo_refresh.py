"""Refreshing the public demo: only demo restaurants are replaced, and only by the scheduler."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.models import InventoryMovement, Order, Restaurant, User
from app.seed import demo as demo_seed
from tests.conftest import Factory


def test_refresh_replaces_only_demo_restaurants(client: TestClient, factory: Factory, db) -> None:
    # A real restaurant with ledger rows must survive untouched.
    real = factory.restaurant("Real Thai")
    manager = factory.manager(real)
    factory.ingredient(manager, "Rice", "g", stock=1000)
    real_movements = db.scalar(select(func.count()).where(InventoryMovement.restaurant_id == real))

    first = demo_seed.refresh_demo(db, "Refresh-test-pass-1", history_days=7, create_admin=False, forecast=False)
    old_demo = first["restaurant"].id
    assert first["removed"] == 0 and db.scalar(select(func.count()).where(Order.restaurant_id == old_demo)) > 0
    assert db.scalar(select(User).where(User.email == "admin@smartpos.demo")) is None  # no admin on a public demo

    second = demo_seed.refresh_demo(db, "ignored", history_days=7, create_admin=False, forecast=False)
    assert second["removed"] == 1 and second["restaurant"].id != old_demo
    assert db.get(Restaurant, old_demo) is None
    assert db.scalar(select(func.count()).where(InventoryMovement.restaurant_id == old_demo)) == 0
    assert db.scalar(select(func.count()).where(InventoryMovement.restaurant_id == real)) == real_movements
    assert db.get(Restaurant, real) is not None
    # Demo accounts are kept (same password) and now belong to the new demo restaurant.
    r = client.post("/api/v1/auth/token", json={"email": "manager@smartpos.demo", "password": "Refresh-test-pass-1"})
    assert r.status_code == 200


def test_refresh_endpoint_requires_the_scheduler_secret(client: TestClient, monkeypatch) -> None:
    settings = get_settings()
    calls = []
    monkeypatch.setattr(demo_seed, "refresh_demo", lambda db, pw, **kw: calls.append(kw) or {"orders": 3, "removed": 1})
    url = "/api/v1/internal/demo/refresh"

    assert client.get(url).status_code == 404  # not a demo deployment
    monkeypatch.setattr(settings, "demo_login_enabled", True)
    assert client.get(url).status_code == 404  # no CRON_SECRET configured
    monkeypatch.setattr(settings, "cron_secret", "s3cret-value-for-tests")
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"Authorization": "Bearer wrong"}).status_code == 401
    r = client.get(url, headers={"Authorization": "Bearer s3cret-value-for-tests"})
    assert r.status_code == 200 and r.json()["refreshed"] is True
    assert calls == [{"create_admin": False, "set_password": False}]


def test_demo_password_from_env_file_is_applied_to_existing_accounts(
    client: TestClient, db, tmp_path, monkeypatch
) -> None:
    """Re-seeding with a new DEMO_PASSWORD (here from an .env file, with a stray space)
    updates accounts that an earlier run created with another password."""
    import sys

    from app.core.config import Settings

    demo_seed.seed(db, "Old-random-pass-1", history_days=7)

    def token(password: str) -> int:
        r = client.post("/api/v1/auth/token", json={"email": "manager@smartpos.demo", "password": password})
        return r.status_code

    assert token("Old-random-pass-1") == 200
    env = tmp_path / ".env"
    env.write_text("DEMO_PASSWORD= fixture-demo-pass-42\n")
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    settings = Settings(_env_file=str(env))
    assert settings.demo_password == "fixture-demo-pass-42"
    monkeypatch.setattr(demo_seed, "get_settings", lambda: settings)
    monkeypatch.setattr(sys, "argv", ["seed", "--days", "7", "--no-forecast"])
    demo_seed.main()  # the restaurant exists, so only the password is applied
    db.expire_all()

    assert token("fixture-demo-pass-42") == 200
    assert token("Old-random-pass-1") == 401
    admin = client.post("/api/v1/auth/token", json={"email": "admin@smartpos.demo", "password": "fixture-demo-pass-42"})
    assert admin.status_code == 200
