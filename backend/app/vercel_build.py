"""Build step for the backend on Vercel (``[tool.vercel.scripts] build`` in pyproject.toml).

1. Apply database migrations, over the direct (non-pooled) connection when one is
   configured (MIGRATION_DATABASE_URL, DATABASE_URL_UNPOOLED or POSTGRES_URL_NON_POOLING).
2. On a public demo deployment (DEMO_LOGIN_ENABLED=true) that has no demo restaurant
   yet, create it: synthetic history, an initial forecast and no administrator account.

On Vercel it first checks the one thing it cannot work without, a database, and explains
how to connect one. Everything else has an automatic value there (see app/core/config.py).

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


def _value(env: Mapping[str, str], *names: str) -> str:
    return next((env[n].strip() for n in names if env.get(n, "").strip()), "")


def vercel_settings_report(env: Mapping[str, str]) -> tuple[list[str], list[str]]:
    """Settings problems on Vercel, in plain language: (blocking problems, notes).

    Lines are short because Vercel's log viewer cuts long ones off. A missing database is
    not a problem here: the site then deploys and shows the setup steps itself.
    APP_ENV, SECRET_KEY, FRONTEND_URL, CORS_ORIGINS and TRUST_FORWARDED_FOR have
    automatic values on Vercel (see Settings._apply_vercel_defaults).
    """
    problems: list[str] = []
    notes: list[str] = []
    secret = _value(env, "SECRET_KEY")
    if secret and len(secret) < 32:
        problems.append(
            "SECRET_KEY is too short (under 32 characters).\n"
            "    Delete it in Settings > Environment Variables:\n"
            "    a key is then created automatically."
        )
    app_env = _value(env, "APP_ENV").lower()
    if app_env and app_env not in {"production", "development", "test"}:
        problems.append(f"APP_ENV is '{app_env}'.\n    Delete it in Settings > Environment Variables.")
    elif app_env and app_env != "production":
        notes.append(f"APP_ENV is '{app_env}'. Delete it to run in production mode.")
    demo = _value(env, "DEMO_LOGIN_ENABLED").lower()
    if demo in {"0", "false", "no", "off"}:
        notes.append("Demo sign-in is off (DEMO_LOGIN_ENABLED=false).\n  Create an administrator to sign in (docs).")
    elif not _value(env, "CRON_SECRET"):
        notes.append("Optional: add CRON_SECRET (any long random\n  value) so the demo data refreshes every day.")
    return problems, notes


NO_DATABASE = """No database is connected yet.
The site will deploy and show these steps:
  1. Storage tab > Create Database > Neon
  2. Connect it to this project (Production)
  3. Deployments > ... > Redeploy"""


def _say(text: str, *, error: bool = False) -> None:
    for line in text.splitlines():
        print(f"SmartPOS build: {line}", file=sys.stderr if error else sys.stdout)


def _check_vercel_settings(env: Mapping[str, str]) -> bool:
    """Report on the settings; exits on a wrong value. False = no database, skip its steps."""
    problems, notes = vercel_settings_report(env)
    for note in notes:
        _say(f"note: {note}")
    if problems:
        _say("these settings need fixing:", error=True)
        for problem in problems:
            _say(f"  - {problem}", error=True)
        _fail("then redeploy. See docs/DEPLOYMENT.md.")
    if not _value(env, "DATABASE_URL", "POSTGRES_URL"):
        _say(NO_DATABASE)
        return False
    return True


def main() -> None:
    # Vercel sets VERCEL=1 during builds. Checked first: SKIP_MIGRATIONS does not make
    # these settings any less necessary at runtime.
    if os.environ.get("VERCEL") and not _check_vercel_settings(os.environ):
        return
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
    print(f"SmartPOS build: settings OK ({settings.app_env} mode, site address {settings.frontend_url}).")
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
