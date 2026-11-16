"""Production configuration checks and the SMTP email backend."""

from __future__ import annotations

import smtplib

import pytest

from app.core.config import Settings
from app.services import email as email_service

PROD = {
    "app_env": "production",
    "secret_key": "x" * 48,
    "database_url": "postgresql://app:secret@db.internal:5432/smartpos",
    "cors_origins": "https://pos.example.com",
}


def test_production_rejects_insecure_settings() -> None:
    Settings(**PROD)  # a sound configuration loads
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(**{**PROD, "secret_key": "short"})
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings(**{**PROD, "cors_origins": "*"})
    with pytest.raises(ValueError, match="COOKIE_SECURE"):
        Settings(**{**PROD, "cookie_secure": False})
    with pytest.raises(ValueError, match="EMAIL_BACKEND=console"):
        Settings(**{**PROD, "email_backend": "console"})
    with pytest.raises(ValueError, match="SMTP_HOST"):
        Settings(**{**PROD, "email_backend": "smtp"})
    with pytest.raises(ValueError, match="SMTP_SECURITY=none"):
        Settings(**{**PROD, "email_backend": "smtp", "smtp_host": "smtp.example.com", "smtp_security": "none"})
    assert Settings(**PROD).effective_email_backend == "disabled"
    assert Settings(**PROD).secure_cookies is True


class FakeSMTP:
    instances: list[FakeSMTP] = []
    fail = False

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host, self.port, self.calls = host, port, []
        FakeSMTP.instances.append(self)

    def __enter__(self) -> FakeSMTP:
        return self

    def __exit__(self, *exc: object) -> None:
        self.calls.append("quit")

    def starttls(self, context) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append(f"login:{user}")

    def send_message(self, message) -> None:
        if FakeSMTP.fail:
            raise smtplib.SMTPRecipientsRefused({})
        self.calls.append(("send", message["To"], message["Subject"], message.get_content()))


def test_smtp_backend_uses_starttls_and_never_logs_the_body(monkeypatch, caplog) -> None:
    FakeSMTP.instances, FakeSMTP.fail = [], False
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    settings = Settings(
        email_backend="smtp",
        smtp_host="smtp.example.com",
        smtp_username="mailer",
        smtp_password="mail-secret",
        email_from="SmartPOS <no-reply@example.com>",
    )
    sender = email_service.SmtpEmailSender(settings)
    assert sender.send("staff@example.com", "Reset your password", "https://pos/reset?token=SECRET") is True
    server = FakeSMTP.instances[0]
    assert (server.host, server.port) == ("smtp.example.com", 587)
    assert server.calls[:2] == ["starttls", "login:mailer"]
    assert server.calls[2][:3] == ("send", "staff@example.com", "Reset your password")

    FakeSMTP.fail = True
    with caplog.at_level("INFO", logger="smartpos.email"):
        assert sender.send("staff@example.com", "Reset your password", "https://pos/reset?token=SECRET") is False
    assert "SECRET" not in caplog.text and "mail-secret" not in caplog.text


def test_email_backend_selection(monkeypatch) -> None:
    monkeypatch.setattr(email_service, "get_settings", lambda: Settings(email_backend="smtp", smtp_host="h"))
    assert isinstance(email_service.get_email_sender(), email_service.SmtpEmailSender)
    monkeypatch.setattr(email_service, "get_settings", lambda: Settings(app_env="test"))
    assert isinstance(email_service.get_email_sender(), email_service.ConsoleEmailSender)


def test_api_docs_and_hsts_follow_the_environment(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app.core import config
    from app.main import create_app

    assert Settings(**PROD).show_api_docs is False
    assert Settings(**{**PROD, "api_docs_enabled": True}).show_api_docs is True
    assert Settings(app_env="development").show_api_docs is True

    prod = Settings(**PROD)
    monkeypatch.setattr(config, "get_settings", lambda: prod)
    monkeypatch.setattr("app.main.get_settings", lambda: prod)
    monkeypatch.setattr("app.core.middleware.get_settings", lambda: prod)
    with TestClient(create_app()) as client:
        assert client.get("/api/docs").status_code == 404
        assert client.get("/api/v1/openapi.json").status_code == 404
        live = client.get("/api/v1/health")
        assert live.headers["Strict-Transport-Security"].startswith("max-age=")


def test_blank_environment_values_mean_unset(monkeypatch) -> None:
    for name in ("EMAIL_BACKEND", "SMTP_HOST", "OPENAI_API_KEY", "COOKIE_SECURE", "API_DOCS_ENABLED"):
        monkeypatch.setenv(name, "")
    settings = Settings()
    assert settings.email_backend is None and settings.smtp_host is None
    assert settings.openai_api_key is None and settings.llm_configured is False
    assert settings.cookie_secure is None and settings.api_docs_enabled is None


def test_connection_pooler_detection() -> None:
    assert Settings(database_url="postgresql://u:p@localhost:5432/db").uses_connection_pooler is False
    assert Settings(database_url="postgresql://u:p@aws-0-ap.pooler.supabase.com:6543/postgres").uses_connection_pooler
    assert Settings(database_url="postgresql://u:p@ep-cool-1-pooler.us-east-2.aws.neon.tech/db").uses_connection_pooler
    assert Settings(database_url="postgresql://u:p@db.example.com:5432/db", database_pooler=True).uses_connection_pooler


def test_vercel_postgres_integration_urls(monkeypatch) -> None:
    from app.core.config import Settings

    for name in (
        "DATABASE_URL",
        "POSTGRES_URL",
        "MIGRATION_DATABASE_URL",
        "DATABASE_URL_UNPOOLED",
        "POSTGRES_URL_NON_POOLING",
    ):
        monkeypatch.delenv(name, raising=False)
    # Supabase-style variables: pooled URL with client-specific options, plus a direct URL.
    monkeypatch.setenv(
        "POSTGRES_URL", "postgres://u:p%40ss@db.example.supabase.com:6543/postgres?sslmode=require&supa=base-pooler.x"
    )
    monkeypatch.setenv(
        "POSTGRES_URL_NON_POOLING", "postgres://u:p%40ss@db.example.supabase.com:5432/postgres?sslmode=require"
    )
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+psycopg://u:p%40ss@db.example.supabase.com:6543/postgres?sslmode=require"
    assert s.uses_connection_pooler is True
    assert s.effective_migration_url.endswith(":5432/postgres?sslmode=require")

    # DATABASE_URL wins over POSTGRES_URL; without a direct URL, migrations use DATABASE_URL.
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://app:secret@ep-x-pooler.neon.tech/smartpos?pgbouncer=true&sslmode=require"
    )
    monkeypatch.delenv("POSTGRES_URL_NON_POOLING")
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+psycopg://app:secret@ep-x-pooler.neon.tech/smartpos?sslmode=require"
    assert s.effective_migration_url == s.database_url
    monkeypatch.setenv("MIGRATION_DATABASE_URL", "")
    assert Settings(_env_file=None).migration_database_url is None
