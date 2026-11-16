"""Public demo sign-in for portfolio deployments (``DEMO_LOGIN_ENABLED``).

Visitors choose a role and are signed in to the demo restaurant's account for
that role: no password is shown or needed. Only manager, cashier and kitchen
accounts of a restaurant marked ``is_demo`` qualify, never a platform
administrator. While demo sign-in is enabled, accounts that belong only to demo
restaurants cannot change their sign-in details or manage staff, so one visitor
cannot lock the next one out or use the demo to create accounts for real email
addresses.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Forbidden, NotFound
from app.models import Restaurant, RestaurantMembership, User
from app.models.enums import RestaurantRole
from app.schemas.auth import DemoInfo, DemoRole

ROLES: dict[str, tuple[str, str]] = {
    "MANAGER": ("Manager", "Dashboard, stock, forecasts and reports"),
    "CASHIER": ("Cashier", "POS, orders, tables and payments"),
    "KITCHEN": ("Kitchen", "Live kitchen display"),
}


def demo_restaurant(db: Session) -> Restaurant | None:
    return db.scalar(
        select(Restaurant)
        .where(Restaurant.is_demo.is_(True), Restaurant.is_active.is_(True))
        .order_by(Restaurant.created_at)
        .limit(1)
    )


def demo_user(db: Session, restaurant: Restaurant, role: str) -> User | None:
    return db.scalar(
        select(User)
        .join(RestaurantMembership, RestaurantMembership.user_id == User.id)
        .where(
            RestaurantMembership.restaurant_id == restaurant.id,
            RestaurantMembership.role == RestaurantRole(role),
            RestaurantMembership.is_active.is_(True),
            User.is_active.is_(True),
            User.is_platform_admin.is_(False),
        )
        .order_by(User.created_at)
        .limit(1)
    )


def info(db: Session) -> DemoInfo:
    if not get_settings().demo_login_enabled:
        return DemoInfo(enabled=False)
    restaurant = demo_restaurant(db)
    if restaurant is None:
        return DemoInfo(enabled=False)
    roles = [
        DemoRole(role=role, label=label, description=description)  # type: ignore[arg-type]
        for role, (label, description) in ROLES.items()
        if demo_user(db, restaurant, role) is not None
    ]
    return DemoInfo(enabled=bool(roles), restaurant_name=restaurant.name, roles=roles)


def account_for(db: Session, role: str) -> User:
    if not get_settings().demo_login_enabled:
        raise NotFound("Demo sign-in is not enabled on this server.", code="demo_disabled")
    restaurant = demo_restaurant(db)
    user = demo_user(db, restaurant, role) if restaurant else None
    if user is None:
        raise NotFound("No demo account is available for that role.", code="demo_unavailable")
    return user


def is_shared_demo_account(db: Session, user: User) -> bool:
    """True when demo sign-in is on and the user belongs only to demo restaurants."""
    if not get_settings().demo_login_enabled or user.is_platform_admin:
        return False
    flags = db.scalars(
        select(Restaurant.is_demo)
        .join(RestaurantMembership, RestaurantMembership.restaurant_id == Restaurant.id)
        .where(RestaurantMembership.user_id == user.id)
    ).all()
    return bool(flags) and all(flags)


def ensure_not_shared_demo_account(db: Session, user: User) -> None:
    if is_shared_demo_account(db, user):
        raise Forbidden(
            "This is a shared demo account: sign-in details and staff accounts cannot be changed.",
            code="demo_restricted",
        )
