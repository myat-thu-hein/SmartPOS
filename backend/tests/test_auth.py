"""Authentication, sessions, CSRF, rate limiting and password reset."""

from __future__ import annotations

import logging

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.rate_limit import login_limiter
from app.models import AuditLog, PasswordResetToken, User
from tests.conftest import PASSWORD, Factory


def _login_cookie(client: TestClient, email: str, password: str = PASSWORD, headers: dict[str, str] | None = None):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password}, headers=headers)


def test_health_endpoints(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.headers["X-Request-ID"]
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    ready = client.get("/api/v1/health/ready")
    assert ready.status_code == 200
    assert ready.json()["checks"]["database"] == "ok"


def test_login_sets_httponly_cookie_and_me_works(client: TestClient, factory: Factory) -> None:
    rid = factory.restaurant("Baan Thai")
    actor = factory.manager(rid)
    r = _login_cookie(client, actor.email)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == actor.email
    assert body["memberships"][0]["role"] == "MANAGER"
    assert "menu:write" in body["memberships"][0]["permissions"]
    set_cookie = r.headers.get_list("set-cookie")
    session_cookie = next(c for c in set_cookie if c.startswith(get_settings().session_cookie_name + "="))
    assert "HttpOnly" in session_cookie
    assert "SameSite=lax" in session_cookie or "samesite=lax" in session_cookie.lower()
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["id"] == str(actor.user_id)
    # Password hash is never exposed.
    assert "password" not in me.text


def test_invalid_credentials_are_rejected_without_enumeration(client: TestClient, factory: Factory, db) -> None:
    rid = factory.restaurant()
    actor = factory.cashier(rid)
    wrong_password = _login_cookie(client, actor.email, "wrong-password1")
    unknown_user = _login_cookie(client, "nobody@example.com", "wrong-password1")
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json()["error"]["message"] == unknown_user.json()["error"]["message"]
    assert db.scalar(select(AuditLog).where(AuditLog.action == "auth.login_failed")) is not None


def test_inactive_user_cannot_log_in(client: TestClient, factory: Factory, db) -> None:
    rid = factory.restaurant()
    actor = factory.cashier(rid)
    user = db.get(User, actor.user_id)
    user.is_active = False
    db.commit()
    assert _login_cookie(client, actor.email).status_code == 401
    # Existing tokens stop working as well.
    assert client.get("/api/v1/auth/me", headers=actor.headers).status_code == 401


def test_cookie_requests_require_csrf_token_for_mutations(client: TestClient, factory: Factory) -> None:
    rid = factory.restaurant()
    actor = factory.manager(rid)
    login = _login_cookie(client, actor.email)
    csrf = login.json()["csrf_token"]
    headers = {"X-Restaurant-ID": str(rid)}
    missing = client.post("/api/v1/categories", json={"name": "Drinks"}, headers=headers)
    assert missing.status_code == 403
    assert missing.json()["error"]["code"] == "csrf_failed"
    wrong = client.post("/api/v1/categories", json={"name": "Drinks"}, headers={**headers, "X-CSRF-Token": "x" * 32})
    assert wrong.status_code == 403
    ok = client.post("/api/v1/categories", json={"name": "Drinks"}, headers={**headers, "X-CSRF-Token": csrf})
    assert ok.status_code == 201, ok.text


def test_bearer_token_requests_do_not_need_csrf(client: TestClient, factory: Factory) -> None:
    rid = factory.restaurant()
    actor = factory.manager(rid)
    r = client.post("/api/v1/categories", json={"name": "Desserts"}, headers=actor.headers)
    assert r.status_code == 201


def test_logout_revokes_session(client: TestClient, factory: Factory) -> None:
    rid = factory.restaurant()
    actor = factory.cashier(rid)
    assert client.post("/api/v1/auth/logout", headers=actor.headers).status_code == 200
    assert client.get("/api/v1/auth/me", headers=actor.headers).status_code == 401


def test_unauthenticated_access_is_rejected(client: TestClient) -> None:
    r = client.get("/api/v1/products")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_login_rate_limit(client: TestClient, factory: Factory, monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "login_rate_limit_attempts", 3)
    login_limiter.reset()
    for _ in range(3):
        assert _login_cookie(client, "victim@example.com", "bad-password1").status_code == 401
    limited = _login_cookie(client, "victim@example.com", "bad-password1")
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1


def test_login_limits_per_account_and_per_network_separately(client: TestClient, monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "login_rate_limit_attempts", 2)
    monkeypatch.setattr(settings, "login_rate_limit_ip_attempts", 5)
    login_limiter.reset()
    # Staff sharing one connection: several accounts may sign in from the same IP ...
    for i in range(5):
        assert _login_cookie(client, f"staff{i}@example.com", "bad-password1").status_code == 401
    # ... until that network's budget is used up, whichever account is tried next.
    assert _login_cookie(client, "staff9@example.com", "bad-password1").status_code == 429
    login_limiter.reset()
    # One account is protected on its own budget, which is smaller.
    assert _login_cookie(client, "owner@example.com", "bad-password1").status_code == 401
    assert _login_cookie(client, "owner@example.com", "bad-password1").status_code == 401
    assert _login_cookie(client, "owner@example.com", "bad-password1").status_code == 429
    assert _login_cookie(client, "someone@example.com", "bad-password1").status_code == 401


def test_successful_sign_in_clears_the_account_budget(client: TestClient, factory: Factory, monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "login_rate_limit_attempts", 2)
    login_limiter.reset()
    actor = factory.manager(factory.restaurant())  # signs in once through the API
    for _ in range(4):  # one person on several devices
        assert _login_cookie(client, actor.email, PASSWORD).status_code == 200
    assert _login_cookie(client, actor.email, "wrong-password1").status_code == 401
    assert _login_cookie(client, actor.email, "wrong-password1").status_code == 401
    assert _login_cookie(client, actor.email, PASSWORD).status_code == 429  # guessing still locks the account


def test_keep_me_signed_in_controls_cookie_lifetime(client: TestClient, factory: Factory) -> None:
    actor = factory.manager(factory.restaurant())
    remembered = client.post("/api/v1/auth/login", json={"email": actor.email, "password": PASSWORD})
    cookies = remembered.headers.get_list("set-cookie")
    assert remembered.status_code == 200 and len(cookies) == 2
    assert all("Max-Age=" in c for c in cookies)
    session_only = client.post(
        "/api/v1/auth/login", json={"email": actor.email, "password": PASSWORD, "remember": False}
    )
    cookies = session_only.headers.get_list("set-cookie")
    assert session_only.status_code == 200 and len(cookies) == 2
    assert not any("Max-Age=" in c or "expires=" in c.lower() for c in cookies)  # gone when the browser closes
    assert any("HttpOnly" in c for c in cookies)


def test_change_password_revokes_other_sessions(client: TestClient, factory: Factory) -> None:
    rid = factory.restaurant()
    actor = factory.manager(rid)
    other = client.post("/api/v1/auth/token", json={"email": actor.email, "password": PASSWORD}).json()
    weak = client.post(
        "/api/v1/auth/change-password",
        headers=actor.headers,
        json={"current_password": PASSWORD, "new_password": "short"},
    )
    assert weak.status_code == 422
    r = client.post(
        "/api/v1/auth/change-password",
        headers=actor.headers,
        json={"current_password": PASSWORD, "new_password": "N3w-password-123"},
    )
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/auth/me", headers=actor.headers).status_code == 200
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {other['access_token']}"}).status_code == 401
    )
    assert _login_cookie(client, actor.email, "N3w-password-123").status_code == 200


def test_password_reset_flow(client: TestClient, factory: Factory, db, caplog) -> None:
    rid = factory.restaurant()
    actor = factory.cashier(rid)
    caplog.set_level(logging.INFO, logger="smartpos.email")
    unknown = client.post("/api/v1/auth/password-reset/request", json={"email": "ghost@example.com"})
    known = client.post("/api/v1/auth/password-reset/request", json={"email": actor.email})
    assert unknown.status_code == known.status_code == 202
    assert unknown.json() == known.json()
    log_text = "\n".join(r.getMessage() for r in caplog.records)
    token = log_text.split("token=")[1].split()[0]
    stored = db.scalar(select(PasswordResetToken))
    assert stored is not None and token not in stored.token_hash  # only a digest is stored
    bad = client.post("/api/v1/auth/password-reset/confirm", json={"token": "x" * 20, "new_password": "Abcdef12345"})
    assert bad.status_code == 422
    ok = client.post("/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": "Brand-new-pass1"})
    assert ok.status_code == 200, ok.text
    # Tokens are single use and old sessions are revoked.
    again = client.post("/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": "Another-pass12"})
    assert again.status_code == 422
    assert client.get("/api/v1/auth/me", headers=actor.headers).status_code == 401
    assert _login_cookie(client, actor.email, "Brand-new-pass1").status_code == 200


def test_validation_errors_use_consistent_format(client: TestClient) -> None:
    r = client.post("/api/v1/auth/login", json={"email": "not-an-email", "password": ""})
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "validation_error"
    assert {d["field"] for d in error["details"]} >= {"email", "password"}
    assert error["request_id"]


def test_password_policy_counts_combining_marks_as_letters() -> None:
    from app.core.security import validate_password_strength

    assert validate_password_strength("Strong-pass-42") == []
    assert validate_password_strength("12345678")
    assert validate_password_strength("onlyletters")
    # Thai vowel and tone marks are combining characters; a Thai word is still letters only.
    assert validate_password_strength("รหัสผ่านไทยยาว")
    assert validate_password_strength("รหัสผ่าน2026") == []


def test_rate_limits_are_shared_across_processes() -> None:
    from app.core.rate_limit import DatabaseRateLimiter

    # Two limiter objects stand in for two backend processes or serverless instances.
    first, second = DatabaseRateLimiter(), DatabaseRateLimiter()
    results = [(first if i % 2 else second).hit("test:shared", limit=3, window_seconds=60) for i in range(4)]
    assert [allowed for allowed, _ in results] == [True, True, True, False]
    retry_after = results[-1][1]
    assert 1 <= retry_after <= 60
    # Other keys are unaffected, and a reset clears the key.
    assert first.hit("test:other", limit=3, window_seconds=60) == (True, 0)
    first.reset("test:shared")
    assert second.hit("test:shared", limit=3, window_seconds=60) == (True, 0)


def test_client_ip_uses_forwarded_for_only_when_trusted(client: TestClient, factory: Factory, db, monkeypatch) -> None:
    from sqlalchemy import select

    from app.models import AuditLog

    settings = get_settings()

    def last_login_ip() -> str | None:
        return db.scalar(select(AuditLog.ip_address).order_by(AuditLog.created_at.desc()).limit(1))

    spoofed = {"X-Forwarded-For": "203.0.113.7, 10.0.0.1"}
    _login_cookie(client, "nobody@example.com", "bad-password1", headers=spoofed)
    assert last_login_ip() != "203.0.113.7"
    monkeypatch.setattr(settings, "trust_forwarded_for", True)
    _login_cookie(client, "nobody@example.com", "bad-password1", headers=spoofed)
    assert last_login_ip() == "203.0.113.7"
