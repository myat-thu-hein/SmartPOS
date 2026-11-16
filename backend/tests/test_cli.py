"""Administrator bootstrap command."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import cli
from tests.conftest import PASSWORD, Factory


def test_create_admin_reads_password_from_environment(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("BOOTSTRAP_PW", "short")
    with pytest.raises(SystemExit, match="at least"):
        cli.create_admin("ops@example.com", "Ops", "BOOTSTRAP_PW", promote=False)
    monkeypatch.setenv("BOOTSTRAP_PW", "Strong-pass-42")
    assert "Created" in cli.create_admin("Ops@Example.com", "Ops", "BOOTSTRAP_PW", promote=False)

    login = client.post("/api/v1/auth/login", json={"email": "ops@example.com", "password": "Strong-pass-42"})
    assert login.status_code == 200, login.text
    assert login.json()["user"]["is_platform_admin"] is True
    with pytest.raises(SystemExit, match="already exists"):
        cli.create_admin("ops@example.com", "Ops", "BOOTSTRAP_PW", promote=False)


def test_create_admin_refuses_missing_password_and_promotes_existing(
    client: TestClient, factory: Factory, monkeypatch
) -> None:
    monkeypatch.delenv("MISSING_PW", raising=False)
    with pytest.raises(SystemExit, match="MISSING_PW"):
        cli.create_admin("new@example.com", "New", "MISSING_PW", promote=False)
    rid = factory.restaurant()
    manager = factory.manager(rid)
    assert "now a platform administrator" in cli.create_admin(manager.email, "x", None, promote=True)
    # Promotion keeps the user's own password.
    login = client.post("/api/v1/auth/login", json={"email": manager.email, "password": PASSWORD})
    assert login.status_code == 200 and login.json()["user"]["is_platform_admin"] is True
