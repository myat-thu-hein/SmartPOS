"""Authentication: credentials, server-side sessions and password resets."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ValidationFailed
from app.core.security import (
    generate_token,
    hash_password,
    hash_token,
    needs_rehash,
    validate_password_strength,
    verify_password,
)
from app.models import PasswordResetToken, User, UserSession
from app.services.audit import record_audit
from app.services.email import get_email_sender

SESSION_TOUCH_INTERVAL = timedelta(minutes=5)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == normalize_email(email)))


def ensure_password_strength(password: str) -> None:
    problems = validate_password_strength(password)
    if problems:
        raise ValidationFailed(" ".join(problems), details=[{"field": "password", "message": p} for p in problems])


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    # verify_password always runs a hash comparison, so response time does not
    # reveal whether the account exists.
    valid = verify_password(password, user.password_hash if user else None)
    if not user or not valid or not user.is_active:
        return None
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    return user


@dataclass
class IssuedSession:
    session: UserSession
    token: str
    csrf_token: str


def create_session(db: Session, user: User, *, ip: str | None, user_agent: str | None) -> IssuedSession:
    settings = get_settings()
    token = generate_token()
    csrf_token = generate_token(24)
    now = datetime.now(UTC)
    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        csrf_token_hash=hash_token(csrf_token),
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
        last_seen_at=now,
        ip_address=ip,
        user_agent=(user_agent or "")[:300] or None,
    )
    user.last_login_at = now
    db.add(session)
    db.flush()
    return IssuedSession(session=session, token=token, csrf_token=csrf_token)


def resolve_session(db: Session, token: str) -> UserSession | None:
    if not token or len(token) > 200:
        return None
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if session is None or session.revoked_at is not None:
        return None
    now = datetime.now(UTC)
    if session.expires_at <= now:
        return None
    if not session.user.is_active:
        return None
    if session.last_seen_at is None or now - session.last_seen_at > SESSION_TOUCH_INTERVAL:
        session.last_seen_at = now
        db.commit()
    return session


def revoke_session(db: Session, session: UserSession) -> None:
    session.revoked_at = datetime.now(UTC)


def revoke_all_sessions(db: Session, user_id: uuid.UUID, *, except_session_id: uuid.UUID | None = None) -> None:
    stmt = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if except_session_id is not None:
        stmt = stmt.where(UserSession.id != except_session_id)
    db.execute(stmt.values(revoked_at=datetime.now(UTC)))


def change_password(
    db: Session, user: User, current_password: str, new_password: str, current_session_id: uuid.UUID | None
) -> None:
    if not verify_password(current_password, user.password_hash):
        raise ValidationFailed("The current password is incorrect.", code="invalid_password")
    ensure_password_strength(new_password)
    user.password_hash = hash_password(new_password)
    revoke_all_sessions(db, user.id, except_session_id=current_session_id)
    record_audit(db, action="auth.password_changed", actor_user_id=user.id, entity_type="user", entity_id=user.id)


def request_password_reset(db: Session, email: str, *, ip: str | None) -> None:
    """Create a reset token and email it. Always behaves the same whether or not
    the account exists, to avoid account enumeration."""
    user = get_user_by_email(db, email)
    if user is None or not user.is_active:
        return
    settings = get_settings()
    token = generate_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(minutes=settings.password_reset_ttl_minutes),
        )
    )
    record_audit(
        db,
        action="auth.password_reset_requested",
        actor_user_id=user.id,
        entity_type="user",
        entity_id=user.id,
        ip_address=ip,
    )
    db.commit()
    link = f"{settings.frontend_url.rstrip('/')}/reset-password?token={token}"
    get_email_sender().send(
        user.email,
        "Reset your SmartPOS AI password",
        f"Hello {user.full_name},\n\nUse this link within {settings.password_reset_ttl_minutes} minutes "
        f"to choose a new password:\n{link}\n\nIf you did not request this, ignore this email.",
    )


def confirm_password_reset(db: Session, token: str, new_password: str) -> None:
    reset = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token)).with_for_update()
    )
    now = datetime.now(UTC)
    if reset is None or reset.used_at is not None or reset.expires_at <= now:
        raise ValidationFailed("This password reset link is invalid or has expired.", code="invalid_token")
    ensure_password_strength(new_password)
    user = db.get(User, reset.user_id)
    if user is None or not user.is_active:
        raise ValidationFailed("This password reset link is invalid or has expired.", code="invalid_token")
    user.password_hash = hash_password(new_password)
    reset.used_at = now
    revoke_all_sessions(db, user.id)
    record_audit(
        db, action="auth.password_reset_completed", actor_user_id=user.id, entity_type="user", entity_id=user.id
    )
    db.commit()
