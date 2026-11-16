"""Test fixtures.

Tests run against an isolated PostgreSQL database (TEST_DATABASE_URL, default
``smartpos_test`` on localhost). The schema is rebuilt with the real Alembic
migrations at the start of the session, and every table is truncated before
each test. As a safety guard the database name must end with ``_test``.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal

import pytest

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://smartpos:smartpos@localhost:5432/smartpos_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["APP_ENV"] = "test"
os.environ["OPENAI_API_KEY"] = ""
os.environ["LOG_FORMAT"] = "console"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["LOGIN_RATE_LIMIT_ATTEMPTS"] = "1000"

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from argon2 import PasswordHasher  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.core.security as security  # noqa: E402
import app.models  # noqa: E402, F401  (registers tables)
from app.core.config import get_settings  # noqa: E402
from app.core.rate_limit import login_limiter  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_session_factory, reset_engine  # noqa: E402

# Fast, test-only password hashing parameters.
security._hasher = PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1)
security._DUMMY_HASH = security._hasher.hash("dummy")

PASSWORD = "Passw0rd!test"
_PASSWORD_HASH = security.hash_password(PASSWORD)


def _assert_test_database(url: str) -> None:
    name = make_url(url).database or ""
    if not name.endswith("_test"):
        raise RuntimeError(f"Refusing to run tests against database '{name}': name must end with '_test'.")


@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    _assert_test_database(TEST_DATABASE_URL)
    get_settings.cache_clear()
    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    config = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    config.attributes["database_url"] = TEST_DATABASE_URL
    command.upgrade(config, "head")
    engine.dispose()
    reset_engine()
    yield
    reset_engine()


TABLES = ", ".join(t.name for t in Base.metadata.sorted_tables)


@pytest.fixture(autouse=True)
def _clean_tables() -> Iterator[None]:
    login_limiter.reset()
    with get_session_factory()() as s:
        s.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
        s.commit()
    yield


@pytest.fixture
def db() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as c:
        yield c


# --------------------------------------------------------------------------- factories


@dataclass
class Actor:
    user_id: uuid.UUID
    email: str
    token: str
    restaurant_id: uuid.UUID | None

    @property
    def headers(self) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self.token}"}
        if self.restaurant_id:
            h["X-Restaurant-ID"] = str(self.restaurant_id)
        return h

    def for_restaurant(self, restaurant_id: uuid.UUID) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "X-Restaurant-ID": str(restaurant_id)}


class Factory:
    def __init__(self, db: Session, client: TestClient) -> None:
        self.db = db
        self.client = client

    def restaurant(self, name: str | None = None, **settings: object) -> uuid.UUID:
        from app.models import Restaurant
        from app.services.restaurants import initialise_restaurant_defaults

        restaurant = Restaurant(name=name or f"Restaurant {uuid.uuid4().hex[:6]}", **settings)
        self.db.add(restaurant)
        self.db.flush()
        initialise_restaurant_defaults(self.db, restaurant)
        self.db.commit()
        return restaurant.id

    def user(
        self, role: str | None, restaurant_id: uuid.UUID | None, *, admin: bool = False, email: str | None = None
    ) -> Actor:
        from app.models import RestaurantMembership, User
        from app.models.enums import RestaurantRole

        email = email or f"{(role or 'admin').lower()}-{uuid.uuid4().hex[:8]}@example.com"
        user = User(
            email=email, full_name=f"{role or 'Admin'} User", password_hash=_PASSWORD_HASH, is_platform_admin=admin
        )
        self.db.add(user)
        self.db.flush()
        if role and restaurant_id:
            self.db.add(RestaurantMembership(restaurant_id=restaurant_id, user_id=user.id, role=RestaurantRole(role)))
        self.db.commit()
        response = self.client.post("/api/v1/auth/token", json={"email": email, "password": PASSWORD})
        assert response.status_code == 200, response.text
        return Actor(user_id=user.id, email=email, token=response.json()["access_token"], restaurant_id=restaurant_id)

    def manager(self, restaurant_id: uuid.UUID) -> Actor:
        return self.user("MANAGER", restaurant_id)

    def cashier(self, restaurant_id: uuid.UUID) -> Actor:
        return self.user("CASHIER", restaurant_id)

    def kitchen(self, restaurant_id: uuid.UUID) -> Actor:
        return self.user("KITCHEN", restaurant_id)

    def admin(self) -> Actor:
        return self.user(None, None, admin=True)

    # Catalog helpers going through the public API (exercises validation too).
    def category(self, actor: Actor, name: str = "Mains") -> dict:
        r = self.client.post("/api/v1/categories", json={"name": name}, headers=actor.headers)
        assert r.status_code == 201, r.text
        return r.json()

    def product(
        self, actor: Actor, category_id: str, name: str = "Pad Thai", price_minor: int = 12000, **extra: object
    ) -> dict:
        r = self.client.post(
            "/api/v1/products",
            json={"name": name, "category_id": category_id, "price_minor": price_minor, **extra},
            headers=actor.headers,
        )
        assert r.status_code == 201, r.text
        return r.json()

    def ingredient(
        self, actor: Actor, name: str, base_unit: str = "g", stock: Decimal | int | None = None, **extra: object
    ) -> dict:
        payload: dict[str, object] = {"name": name, "base_unit": base_unit, **extra}
        if stock is not None:
            payload["opening_stock"] = str(stock)
        r = self.client.post("/api/v1/ingredients", json=payload, headers=actor.headers)
        assert r.status_code == 201, r.text
        return r.json()

    def recipe(self, actor: Actor, product_id: str, items: list[dict]) -> dict:
        r = self.client.put(f"/api/v1/recipes/products/{product_id}", json={"items": items}, headers=actor.headers)
        assert r.status_code == 200, r.text
        return r.json()

    def table(self, actor: Actor, name: str = "T1", capacity: int = 4) -> dict:
        r = self.client.post("/api/v1/tables", json={"name": name, "capacity": capacity}, headers=actor.headers)
        assert r.status_code == 201, r.text
        return r.json()

    def payment_method_id(self, actor: Actor, code: str = "CASH") -> str:
        r = self.client.get("/api/v1/payments/methods", headers=actor.headers)
        assert r.status_code == 200, r.text
        return next(m["id"] for m in r.json() if m["code"] == code)


@pytest.fixture
def factory(db: Session, client: TestClient) -> Factory:
    return Factory(db, client)
