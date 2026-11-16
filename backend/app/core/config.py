"""Application configuration loaded from environment variables.

All configuration is validated at startup. In production, insecure defaults are
rejected with an actionable error message instead of silently being used.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

DEV_SECRET_KEY = "dev-insecure-secret-key-change-me-0123456789"  # noqa: S105 (rejected in production)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "SmartPOS AI"
    app_version: str = "1.0.0"
    app_env: Literal["development", "test", "production"] = "development"

    # POSTGRES_URL is what the Vercel Postgres integrations (Neon, Supabase) provide.
    database_url: str = Field(
        default="postgresql+psycopg://smartpos:smartpos@localhost:5432/smartpos",
        validation_alias=AliasChoices("DATABASE_URL", "POSTGRES_URL"),
    )
    # Direct (non-pooled) connection for migrations; falls back to DATABASE_URL.
    migration_database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MIGRATION_DATABASE_URL", "DATABASE_URL_UNPOOLED", "POSTGRES_URL_NON_POOLING"),
    )
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_echo: bool = False
    # true/false to force; unset = detect from DATABASE_URL (port 6543 or a "-pooler" host).
    database_pooler: bool | None = None

    secret_key: str = DEV_SECRET_KEY
    session_ttl_hours: int = Field(default=12, ge=1, le=24 * 30)
    session_cookie_name: str = "smartpos_session"
    csrf_cookie_name: str = "smartpos_csrf"
    cookie_secure: bool | None = None
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_domain: str | None = None

    cors_origins: str = "http://localhost:3000"
    frontend_url: str = "http://localhost:3000"

    # Trust the first X-Forwarded-For entry. Only safe when clients cannot reach the
    # backend directly (private Vercel service, internal Docker network).
    trust_forwarded_for: bool = False
    # Public "try the demo" sign-in for a portfolio deployment. Off by default; it signs
    # visitors into the demo restaurant's manager, cashier or kitchen account (never an
    # administrator) and blocks changes to those shared accounts.
    demo_login_enabled: bool = False
    # Password for the demo accounts (manager@/cashier@/kitchen@/admin@smartpos.demo).
    # Applied when the demo is seeded, refreshed or re-seeded; unset = a random one.
    demo_password: str | None = None
    # Vercel Cron sends "Authorization: Bearer <CRON_SECRET>"; required by the demo refresh job.
    cron_secret: str | None = None

    # Live updates: each Server-Sent Events connection lasts this long, then the browser
    # reconnects (keep it below the platform's request limit, e.g. 300 s on Vercel).
    events_stream_seconds: int = Field(default=240, ge=10, le=3600)
    events_poll_interval_seconds: float = Field(default=1.0, ge=0.2, le=10)

    # Per account (password guessing) and per client IP (one host trying many accounts).
    # The IP budget is larger because a restaurant's staff often share one connection.
    login_rate_limit_attempts: int = 10
    login_rate_limit_ip_attempts: int = 60
    login_rate_limit_window_seconds: int = 300
    password_reset_ttl_minutes: int = 30
    email_backend: Literal["console", "smtp", "disabled"] | None = None
    email_from: str = "SmartPOS AI <no-reply@localhost>"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_timeout_seconds: float = 15.0

    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    openai_timeout_seconds: float = 30.0
    openai_base_url: str | None = None

    # Interactive API docs (/api/docs, /api/redoc). Default: on, except in production.
    api_docs_enabled: bool | None = None

    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    @field_validator("database_url", "migration_database_url")
    @classmethod
    def _normalise_database_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        # Supabase, Neon and Render hand out URLs using the generic "postgres(ql)://"
        # scheme. SQLAlchemy needs the psycopg (v3) driver to be explicit.
        if value.startswith("postgres://"):
            value = "postgresql://" + value[len("postgres://") :]
        if value.startswith("postgresql://"):
            value = "postgresql+psycopg://" + value[len("postgresql://") :]
        # Integration URLs can carry options meant for other clients (Prisma's
        # "pgbouncer", Supabase's "supa"); libpq rejects unknown parameters.
        url = make_url(value)
        foreign = {"pgbouncer", "supa", "connection_limit", "pool_timeout"} & set(url.query)
        if foreign:
            value = url.difference_update_query(foreign).render_as_string(hide_password=False)
        return value

    @field_validator(
        "openai_api_key",
        "openai_base_url",
        "email_backend",
        "smtp_host",
        "smtp_username",
        "smtp_password",
        "cookie_secure",
        "cookie_domain",
        "api_docs_enabled",
        "database_pooler",
        "cron_secret",
        "migration_database_url",
        "demo_password",
        mode="before",
    )
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        # docker compose passes unset variables as empty strings.
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def _validate_production(self) -> Settings:
        if self.app_env != "production":
            return self
        problems: list[str] = []
        if self.secret_key == DEV_SECRET_KEY or len(self.secret_key) < 32:
            problems.append(
                "SECRET_KEY must be set to a random value of at least 32 characters "
                '(generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))")'
            )
        if "smartpos:smartpos@localhost" in self.database_url:
            problems.append("DATABASE_URL must point at the production database")
        if self.cookie_secure is False:
            problems.append("COOKIE_SECURE cannot be false in production")
        if "*" in self.cors_origin_list:
            problems.append("CORS_ORIGINS cannot contain '*' in production")
        if self.email_backend == "console":
            problems.append("EMAIL_BACKEND=console writes password reset links to the logs; use smtp or disabled")
        if self.email_backend == "smtp" and not self.smtp_host:
            problems.append("EMAIL_BACKEND=smtp requires SMTP_HOST")
        if self.email_backend == "smtp" and self.smtp_security == "none":
            problems.append("SMTP_SECURITY=none would send reset links unencrypted; use starttls or ssl")
        if self.cookie_samesite == "none" and self.cookie_secure is False:
            problems.append("COOKIE_SAMESITE=none requires secure cookies")
        if problems:
            raise ValueError("Invalid production configuration: " + "; ".join(problems))
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def secure_cookies(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.is_production

    @property
    def effective_email_backend(self) -> str:
        if self.email_backend:
            return self.email_backend
        return "disabled" if self.is_production else "console"

    @property
    def effective_migration_url(self) -> str:
        return self.migration_database_url or self.database_url

    @property
    def uses_connection_pooler(self) -> bool:
        if self.database_pooler is not None:
            return self.database_pooler
        url = make_url(self.database_url)
        return url.port == 6543 or "-pooler" in (url.host or "")

    @property
    def show_api_docs(self) -> bool:
        return self.api_docs_enabled if self.api_docs_enabled is not None else not self.is_production

    @property
    def llm_configured(self) -> bool:
        return self.openai_api_key is not None


@lru_cache
def get_settings() -> Settings:
    return Settings()
