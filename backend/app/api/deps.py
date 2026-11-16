"""FastAPI dependencies: authentication, CSRF, tenant context and permissions.

Authentication accepts either the httpOnly session cookie (browsers) or an
``Authorization: Bearer`` token (API clients). Cookie-authenticated requests
that change state must send the session-bound CSRF token in ``X-CSRF-Token``.

The active restaurant is selected with the ``X-Restaurant-ID`` header and is
always verified against the user's memberships - a client-supplied identifier
is never enough on its own.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Forbidden, NotFound, Unauthorized, ValidationFailed
from app.core.permissions import Permission, permissions_for
from app.core.security import tokens_match
from app.db.session import get_db
from app.models import Restaurant, RestaurantMembership, User, UserSession
from app.models.enums import RestaurantRole
from app.services.auth import resolve_session

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
RESTAURANT_HEADER = "X-Restaurant-ID"


def client_ip(request: Request) -> str | None:
    """The caller's IP address, used for rate limits and audit entries.

    With TRUST_FORWARDED_FOR=true (only when the backend is reachable solely
    through the frontend proxy, e.g. a private Vercel service), the first
    X-Forwarded-For entry is used. Otherwise the connection address, which
    Uvicorn already rewrites for proxies listed in FORWARDED_ALLOW_IPS.
    """
    if get_settings().trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if forwarded:
            return forwarded[:64]
    return request.client.host if request.client else None


@dataclass
class AuthContext:
    user: User
    session: UserSession
    via_cookie: bool


def get_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    settings = get_settings()
    token: str | None = None
    via_cookie = False
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
    else:
        token = request.cookies.get(settings.session_cookie_name)
        via_cookie = token is not None
    if not token:
        raise Unauthorized("Authentication required.")
    session = resolve_session(db, token)
    if session is None:
        raise Unauthorized("Your session has expired. Please sign in again.", code="session_expired")
    if via_cookie and request.method not in SAFE_METHODS:
        csrf = request.headers.get("X-CSRF-Token", "")
        if not csrf or not tokens_match(csrf, session.csrf_token_hash):
            raise Forbidden("Missing or invalid CSRF token.", code="csrf_failed")
    return AuthContext(user=session.user, session=session, via_cookie=via_cookie)


def get_current_user(auth: AuthContext = Depends(get_auth)) -> User:
    return auth.user


@dataclass
class RestaurantContext:
    user: User
    restaurant: Restaurant
    role: RestaurantRole | None
    permissions: frozenset[Permission]
    ip: str | None = None
    extra: dict[str, object] = field(default_factory=dict)

    @property
    def restaurant_id(self) -> uuid.UUID:
        return self.restaurant.id

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id

    @property
    def is_platform_admin(self) -> bool:
        return self.user.is_platform_admin

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions

    def require(self, permission: Permission) -> None:
        if permission not in self.permissions:
            raise Forbidden(
                "You do not have permission to perform this action.", details={"required_permission": permission.value}
            )


def _parse_restaurant_id(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise ValidationFailed(f"{RESTAURANT_HEADER} must be a valid restaurant id.") from exc


def resolve_restaurant_context(
    db: Session, user: User, restaurant_id: uuid.UUID | None, ip: str | None = None
) -> RestaurantContext:
    memberships = db.scalars(
        select(RestaurantMembership).where(
            RestaurantMembership.user_id == user.id, RestaurantMembership.is_active.is_(True)
        )
    ).all()
    if restaurant_id is None:
        if len(memberships) == 1:
            restaurant_id = memberships[0].restaurant_id
        else:
            raise ValidationFailed(
                f"Select a restaurant with the {RESTAURANT_HEADER} header.", code="restaurant_required"
            )
    membership = next((m for m in memberships if m.restaurant_id == restaurant_id), None)
    if membership is None and not user.is_platform_admin:
        # Same response whether the restaurant exists or not: do not leak tenants.
        raise Forbidden("You do not have access to this restaurant.", code="restaurant_forbidden")
    restaurant = db.get(Restaurant, restaurant_id)
    if restaurant is None:
        raise (
            NotFound("Restaurant not found.")
            if user.is_platform_admin
            else Forbidden("You do not have access to this restaurant.", code="restaurant_forbidden")
        )
    if not restaurant.is_active and not user.is_platform_admin:
        raise Forbidden("This restaurant is inactive.", code="restaurant_inactive")
    role = membership.role if membership else None
    return RestaurantContext(
        user=user,
        restaurant=restaurant,
        role=role,
        permissions=permissions_for(role, is_platform_admin=user.is_platform_admin),
        ip=ip,
    )


def get_restaurant_context(
    request: Request, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)
) -> RestaurantContext:
    raw = request.headers.get(RESTAURANT_HEADER)
    restaurant_id = _parse_restaurant_id(raw) if raw else None
    return resolve_restaurant_context(db, auth.user, restaurant_id, client_ip(request))


def require(*permissions: Permission) -> Callable[..., RestaurantContext]:
    """Dependency factory: the current user must hold all given permissions in
    the selected restaurant."""

    def dependency(ctx: RestaurantContext = Depends(get_restaurant_context)) -> RestaurantContext:
        for permission in permissions:
            ctx.require(permission)
        return ctx

    return dependency


def require_platform_admin(auth: AuthContext = Depends(get_auth)) -> AuthContext:
    if not auth.user.is_platform_admin:
        raise Forbidden("Administrator access required.")
    return auth
