"""Operational commands.

    python -m app.cli create-admin --email ops@example.com --name "Ops Admin"

The password is read from an interactive prompt, or from the environment
variable named by --password-env for automated provisioning. It is never taken
from the command line, where it would end up in shell history and process lists.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from app.core.security import hash_password, validate_password_strength
from app.db.session import get_session_factory
from app.models import User
from app.services.audit import record_audit
from app.services.auth import get_user_by_email, normalize_email


def _read_password(env_name: str | None) -> str:
    if env_name:
        password = os.environ.get(env_name, "")
        if not password:
            sys.exit(f"Environment variable {env_name} is empty or not set.")
        return password
    if not sys.stdin.isatty():
        sys.exit("No terminal for a password prompt. Use --password-env VAR_NAME instead.")
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat password: "):
        sys.exit("The passwords do not match.")
    return password


def create_admin(email: str, name: str, password_env: str | None, promote: bool) -> str:
    with get_session_factory()() as db:
        existing = get_user_by_email(db, email)
        if existing is not None:
            if not promote:
                sys.exit("A user with this email already exists. Re-run with --promote to make it an administrator.")
            existing.is_platform_admin = True
            existing.is_active = True
            record_audit(
                db,
                action="user.promoted",
                actor_user_id=None,
                entity_type="user",
                entity_id=existing.id,
                details={"source": "cli", "is_platform_admin": True},
            )
            db.commit()
            return f"{existing.email} is now a platform administrator."
        password = _read_password(password_env)
        problems = validate_password_strength(password)
        if problems:
            sys.exit(" ".join(problems))
        user = User(
            email=normalize_email(email),
            full_name=name,
            password_hash=hash_password(password),
            is_platform_admin=True,
        )
        db.add(user)
        db.flush()
        record_audit(
            db,
            action="user.created",
            actor_user_id=None,
            entity_type="user",
            entity_id=user.id,
            details={"source": "cli", "is_platform_admin": True},
        )
        db.commit()
        return f"Created platform administrator {user.email}."


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="SmartPOS AI operational commands.")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-admin", help="Create (or promote) a platform administrator")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", default="Administrator")
    admin.add_argument("--password-env", metavar="VAR", help="Read the password from this environment variable")
    admin.add_argument("--promote", action="store_true", help="Promote an existing user instead of failing")
    args = parser.parse_args(argv)
    if args.command == "create-admin":
        print(create_admin(args.email, args.name.strip() or "Administrator", args.password_env, args.promote))


if __name__ == "__main__":
    main()
