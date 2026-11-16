"""Staff and platform user management."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RestaurantContext
from app.core.errors import Conflict, Forbidden, NotFound
from app.core.permissions import permissions_for
from app.core.security import hash_password
from app.models import Restaurant, RestaurantMembership, User
from app.models.enums import RestaurantRole
from app.schemas.auth import MembershipOut, StaffCreate, StaffOut, StaffUpdate
from app.services.audit import record_audit
from app.services.auth import ensure_password_strength, get_user_by_email, normalize_email, revoke_all_sessions


def memberships_for(db: Session, user: User) -> list[MembershipOut]:
    if user.is_platform_admin:
        restaurants = db.scalars(select(Restaurant).order_by(Restaurant.name)).all()
        roles = {m.restaurant_id: m.role for m in user.memberships if m.is_active}
        return [
            MembershipOut(
                restaurant_id=r.id,
                restaurant_name=r.name,
                role=roles.get(r.id),
                permissions=sorted(p.value for p in permissions_for(roles.get(r.id), is_platform_admin=True)),
                is_demo=r.is_demo,
                restaurant_active=r.is_active,
            )
            for r in restaurants
        ]
    rows = db.execute(
        select(RestaurantMembership, Restaurant)
        .join(Restaurant, Restaurant.id == RestaurantMembership.restaurant_id)
        .where(
            RestaurantMembership.user_id == user.id,
            RestaurantMembership.is_active.is_(True),
            Restaurant.is_active.is_(True),
        )
        .order_by(Restaurant.name)
    ).all()
    return [
        MembershipOut(
            restaurant_id=r.id,
            restaurant_name=r.name,
            role=m.role,
            permissions=sorted(p.value for p in permissions_for(m.role, is_platform_admin=False)),
            is_demo=r.is_demo,
        )
        for m, r in rows
    ]


def _staff_out(m: RestaurantMembership) -> StaffOut:
    return StaffOut(
        user_id=m.user.id,
        membership_id=m.id,
        email=m.user.email,
        full_name=m.user.full_name,
        role=m.role,
        membership_active=m.is_active,
        user_active=m.user.is_active,
        last_login_at=m.user.last_login_at,
        created_at=m.created_at,
    )


def list_staff(db: Session, ctx: RestaurantContext) -> list[StaffOut]:
    memberships = db.scalars(
        select(RestaurantMembership)
        .where(RestaurantMembership.restaurant_id == ctx.restaurant_id)
        .order_by(RestaurantMembership.role, RestaurantMembership.created_at)
    ).all()
    return [_staff_out(m) for m in memberships]


def _check_role_assignable(ctx: RestaurantContext, role: RestaurantRole) -> None:
    # Managers can manage cashiers and kitchen staff. Only platform admins can
    # grant or revoke the manager role.
    if role == RestaurantRole.MANAGER and not ctx.is_platform_admin:
        raise Forbidden("Only an administrator can assign the manager role.")


def _get_membership(db: Session, ctx: RestaurantContext, user_id: uuid.UUID) -> RestaurantMembership:
    membership = db.scalar(
        select(RestaurantMembership).where(
            RestaurantMembership.restaurant_id == ctx.restaurant_id, RestaurantMembership.user_id == user_id
        )
    )
    if membership is None:
        raise NotFound("Staff member not found.")
    return membership


def create_staff(db: Session, ctx: RestaurantContext, data: StaffCreate) -> StaffOut:
    _check_role_assignable(ctx, data.role)
    if get_user_by_email(db, data.email) is not None:
        # Do not attach existing accounts from other restaurants silently.
        raise Conflict(
            "An account with this email already exists. Ask an administrator to add it to this restaurant.",
            code="email_taken",
        )
    ensure_password_strength(data.password)
    user = User(email=normalize_email(data.email), full_name=data.full_name, password_hash=hash_password(data.password))
    db.add(user)
    db.flush()
    membership = RestaurantMembership(restaurant_id=ctx.restaurant_id, user_id=user.id, role=data.role)
    db.add(membership)
    record_audit(
        db,
        action="staff.created",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="user",
        entity_id=user.id,
        details={"role": data.role.value},
        ip_address=ctx.ip,
    )
    db.commit()
    db.refresh(membership)
    return _staff_out(membership)


def update_staff(db: Session, ctx: RestaurantContext, user_id: uuid.UUID, data: StaffUpdate) -> StaffOut:
    membership = _get_membership(db, ctx, user_id)
    if membership.role == RestaurantRole.MANAGER and not ctx.is_platform_admin and user_id != ctx.user_id:
        raise Forbidden("Only an administrator can change another manager.")
    changes: dict[str, object] = {}
    if data.role is not None and data.role != membership.role:
        _check_role_assignable(ctx, data.role)
        if membership.role == RestaurantRole.MANAGER:
            _check_role_assignable(ctx, membership.role)
        changes["role"] = {"from": membership.role.value, "to": data.role.value}
        membership.role = data.role
    if data.is_active is not None and data.is_active != membership.is_active:
        if user_id == ctx.user_id and not data.is_active:
            raise Forbidden("You cannot deactivate your own access.")
        membership.is_active = data.is_active
        changes["is_active"] = data.is_active
        if not data.is_active:
            revoke_all_sessions(db, user_id)
    if data.full_name is not None and data.full_name != membership.user.full_name:
        membership.user.full_name = data.full_name
        changes["full_name"] = True
    if changes:
        record_audit(
            db,
            action="staff.updated",
            actor_user_id=ctx.user_id,
            restaurant_id=ctx.restaurant_id,
            entity_type="user",
            entity_id=user_id,
            details=changes,
            ip_address=ctx.ip,
        )
    db.commit()
    db.refresh(membership)
    return _staff_out(membership)


def set_staff_password(db: Session, ctx: RestaurantContext, user_id: uuid.UUID, new_password: str) -> None:
    membership = _get_membership(db, ctx, user_id)
    if membership.role == RestaurantRole.MANAGER and not ctx.is_platform_admin and user_id != ctx.user_id:
        raise Forbidden("Only an administrator can reset another manager's password.")
    other_memberships = db.scalars(
        select(RestaurantMembership).where(
            RestaurantMembership.user_id == user_id, RestaurantMembership.restaurant_id != ctx.restaurant_id
        )
    ).all()
    if other_memberships and not ctx.is_platform_admin:
        # The account is shared with another restaurant; this manager does not own it.
        raise Forbidden("This account belongs to several restaurants. Ask an administrator.")
    ensure_password_strength(new_password)
    membership.user.password_hash = hash_password(new_password)
    revoke_all_sessions(db, user_id)
    record_audit(
        db,
        action="staff.password_set",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="user",
        entity_id=user_id,
        ip_address=ctx.ip,
    )
    db.commit()
