"""Build step for the backend on Vercel (``[tool.vercel.scripts] build`` in pyproject.toml).

1. Apply database migrations, over the direct (non-pooled) connection when one is
   configured (MIGRATION_DATABASE_URL, DATABASE_URL_UNPOOLED or POSTGRES_URL_NON_POOLING).
2. On a public demo deployment (DEMO_LOGIN_ENABLED=true) that has no demo restaurant
   yet, create it: synthetic history, an initial forecast and no administrator account.

On Vercel it first checks the settings a deployment cannot work without and lists
anything missing, with where to set it, instead of failing on the first error.

Set SKIP_MIGRATIONS=1 to skip both steps (for example when migrations run elsewhere).
Preview deployments run this too, so give the Preview environment its own database
(the Neon integration can create a branch per preview) rather than production's.
"""

from __future__ import annotations

import os
import secrets
import sys
from collections.abc import Mapping
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _fail(message: str) -> None:
    print(f"SmartPOS build: {message}", file=sys.stderr)
    sys.exit(1)


def vercel_settings_report(env: Mapping[str, str]) -> tuple[list[str], list[str]]:
    """Settings a Vercel deployment needs, in plain language: (missing or unsafe, advisories)."""

    def value(*names: str) -> str:
        return next((env[n].strip() for n in names if env.get(n, "").strip()), "")

    missing: list[str] = []
    advice: list[str] = []
    if value("APP_ENV").lower() != "production":
        missing.append("APP_ENV: set it to production")
    if len(value("SECRET_KEY")) < 32:
        missing.append(
            "SECRET_KEY: a random value of at least 32 characters (mark it Sensitive). Generate one with\n"
            '      python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    if not value("DATABASE_URL", "POSTGRES_URL"):
        missing.append(
            "DATABASE_URL: connect a Postgres database under Storage (the Neon or Supabase integration "
            "sets it for you), or paste a PostgreSQL connection string"
        )
    if not value("FRONTEND_URL"):
        advice.append(
            "FRONTEND_URL is not set, so password-reset links would point at http://localhost:3000. "
            "Set it (and CORS_ORIGINS) to this site's address, e.g. https://<project>.vercel.app"
        )
    if value("DEMO_LOGIN_ENABLED").lower() in {"1", "true", "yes", "on"} and not value("CRON_SECRET"):
        advice.append("DEMO_LOGIN_ENABLED is on but CRON_SECRET is not set, so the daily demo refresh will be refused")
    return missing, advice


def _check_vercel_settings(env: Mapping[str, str]) -> None:
    target = env.get("VERCEL_ENV", "production")
    missing, advice = vercel_settings_report(env)
    for line in advice:
        print(f"SmartPOS build: note: {line}.")
    if missing:
        items = "\n".join(f"  - {line}" for line in missing)
        _fail(
            f"this {target} deployment is missing settings the app needs:\n{items}\n"
            "Add them in Vercel under the project's Settings > Environment Variables, enabled for the "
            f'"{target.capitalize()}" environment, then redeploy. See docs/DEPLOYMENT.md (Option 1: Vercel).'
        )


def main() -> None:
    # Vercel sets VERCEL=1 during builds. Checked first: SKIP_MIGRATIONS does not make
    # these settings any less necessary at runtime.
    if os.environ.get("VERCEL"):
        _check_vercel_settings(os.environ)
    if os.environ.get("SKIP_MIGRATIONS") == "1":
        print("SmartPOS build: SKIP_MIGRATIONS=1, not touching the database.")
        return
    # Import after the early exit so a misconfigured environment still reports clearly.
    from app.core.config import get_settings

    try:
        settings = get_settings()
    except Exception as exc:  # pydantic lists every invalid setting
        _fail(f"configuration is invalid:\n{exc}")
        return
    host = make_url(settings.effective_migration_url).host
    print(f"SmartPOS build: applying migrations on {host} ...")
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    print("SmartPOS build: database schema is up to date.")

    if settings.demo_login_enabled:
        from app.db.session import get_session_factory
        from app.models import Restaurant
        from app.seed import demo as demo_seed

        with get_session_factory()() as db:
            if db.scalar(select(Restaurant.id).where(Restaurant.is_demo.is_(True)).limit(1)):
                print("SmartPOS build: demo restaurant present (the daily refresh keeps it current).")
                return
            print("SmartPOS build: creating the demo restaurant ...")
            password = settings.demo_password or secrets.token_urlsafe(24)
            result = demo_seed.refresh_demo(
                db, password, create_admin=False, set_password=settings.demo_password is not None
            )
            print(f"SmartPOS build: demo restaurant created with {result['orders']} synthetic orders.")


if __name__ == "__main__":
    main()
