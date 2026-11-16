"""Staff management (managers) and platform user management (administrators)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, RestaurantContext, require, require_platform_admin
from app.core.errors import Conflict, Forbidden, NotFound
from app.core.permissions import Permission
from app.core.security import hash_password
from app.db.session import get_db
from app.models import User
from app.schemas.auth import (
    PlatformUserCreate,
    PlatformUserUpdate,
    SetPasswordRequest,
    StaffCreate,
    StaffOut,
    StaffUpdate,
    UserOut,
)
from app.schemas.common import Message, Page, PageParams, paginate
from app.services import demo as demo_service
from app.services import users as user_service
from app.services.audit import record_audit
from app.services.auth import ensure_password_strength, get_user_by_email, normalize_email, revoke_all_sessions

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[StaffOut], summary="List staff of the current restaurant")
def list_staff(
    ctx: RestaurantContext = Depends(require(Permission.STAFF_MANAGE)), db: Session = Depends(get_db)
) -> list[StaffOut]:
    return user_service.list_staff(db, ctx)


@router.post("", response_model=StaffOut, status_code=status.HTTP_201_CREATED)
def create_staff(
    data: StaffCreate, ctx: RestaurantContext = Depends(require(Permission.STAFF_MANAGE)), db: Session = Depends(get_db)
) -> StaffOut:
    demo_service.ensure_not_shared_demo_account(db, ctx.user)
    return user_service.create_staff(db, ctx, data)


@router.patch("/{user_id}", response_model=StaffOut)
def update_staff(
    user_id: uuid.UUID,
    data: StaffUpdate,
    ctx: RestaurantContext = Depends(require(Permission.STAFF_MANAGE)),
    db: Session = Depends(get_db),
) -> StaffOut:
    demo_service.ensure_not_shared_demo_account(db, ctx.user)
    return user_service.update_staff(db, ctx, user_id, data)


@router.post("/{user_id}/password", response_model=Message)
def set_staff_password(
    user_id: uuid.UUID,
    data: SetPasswordRequest,
    ctx: RestaurantContext = Depends(require(Permission.STAFF_MANAGE)),
    db: Session = Depends(get_db),
) -> Message:
    demo_service.ensure_not_shared_demo_account(db, ctx.user)
    user_service.set_staff_password(db, ctx, user_id, data.new_password)
    return Message(message="Password updated and existing sessions signed out.")


@router.get("/all", response_model=Page[UserOut], summary="List all platform users (admin)")
def list_all_users(
    search: str | None = Query(None, max_length=100),
    params: PageParams = Depends(),
    _: AuthContext = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> Page[UserOut]:
    stmt = select(User).order_by(User.created_at.desc())
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(User.email.ilike(like), User.full_name.ilike(like)))
    items, total = paginate(db, stmt, params)
    return Page(
        items=[UserOut.model_validate(u) for u in items], total=total, page=params.page, page_size=params.page_size
    )


@router.post(
    "/platform", response_model=UserOut, status_code=status.HTTP_201_CREATED, summary="Create a platform user (admin)"
)
def create_platform_user(
    data: PlatformUserCreate, auth: AuthContext = Depends(require_platform_admin), db: Session = Depends(get_db)
) -> UserOut:
    if get_user_by_email(db, data.email):
        raise Conflict("An account with this email already exists.", code="email_taken")
    ensure_password_strength(data.password)
    user = User(
        email=normalize_email(data.email),
        full_name=data.full_name,
        password_hash=hash_password(data.password),
        is_platform_admin=data.is_platform_admin,
    )
    db.add(user)
    db.flush()
    record_audit(
        db,
        action="user.created",
        actor_user_id=auth.user.id,
        entity_type="user",
        entity_id=user.id,
        details={"is_platform_admin": data.is_platform_admin},
    )
    db.commit()
    return UserOut.model_validate(user)


@router.patch("/{user_id}/platform", response_model=UserOut, summary="Activate/deactivate or promote a user (admin)")
def update_platform_user(
    user_id: uuid.UUID,
    data: PlatformUserUpdate,
    auth: AuthContext = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("User not found.")
    if user.id == auth.user.id and (data.is_active is False or data.is_platform_admin is False):
        raise Forbidden("You cannot remove your own administrator access.")
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items():
        setattr(user, field, value)
    if changes.get("is_active") is False:
        revoke_all_sessions(db, user.id)
    record_audit(
        db,
        action="user.platform_updated",
        actor_user_id=auth.user.id,
        entity_type="user",
        entity_id=user.id,
        details=changes,
    )
    db.commit()
    return UserOut.model_validate(user)
