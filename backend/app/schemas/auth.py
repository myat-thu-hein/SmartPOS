"""Authentication, user and restaurant schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import RestaurantRole
from app.schemas.common import ORMModel, RequestModel
from app.utils.types import Name


class LoginRequest(RequestModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    # False: the browser forgets the session when it closes (shared tills). The
    # server-side session lifetime (SESSION_TTL_HOURS) applies either way.
    remember: bool = True


class MembershipOut(BaseModel):
    restaurant_id: uuid.UUID
    restaurant_name: str
    role: RestaurantRole | None
    permissions: list[str]
    is_demo: bool = False
    restaurant_active: bool = True


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_platform_admin: bool
    preferred_language: str
    last_login_at: datetime | None
    created_at: datetime


class MeOut(BaseModel):
    user: UserOut
    memberships: list[MembershipOut]


class LoginResponse(MeOut):
    csrf_token: str
    expires_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_at: datetime


class ChangePasswordRequest(RequestModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class PasswordResetRequest(RequestModel):
    email: EmailStr


class PasswordResetConfirm(RequestModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=1, max_length=128)


class UpdateProfileRequest(RequestModel):
    full_name: Name | None = None
    preferred_language: str | None = Field(default=None, pattern="^(en|th)$")


class StaffOut(BaseModel):
    user_id: uuid.UUID
    membership_id: uuid.UUID
    email: str
    full_name: str
    role: RestaurantRole
    membership_active: bool
    user_active: bool
    last_login_at: datetime | None
    created_at: datetime


class StaffCreate(RequestModel):
    email: EmailStr
    full_name: Name
    password: str = Field(min_length=1, max_length=128)
    role: RestaurantRole


class StaffUpdate(RequestModel):
    full_name: Name | None = None
    role: RestaurantRole | None = None
    is_active: bool | None = None


class SetPasswordRequest(RequestModel):
    new_password: str = Field(min_length=1, max_length=128)


class PlatformUserUpdate(RequestModel):
    is_active: bool | None = None
    is_platform_admin: bool | None = None


class PlatformUserCreate(RequestModel):
    email: EmailStr
    full_name: Name
    password: str = Field(min_length=1, max_length=128)
    is_platform_admin: bool = False


class MemberAdd(RequestModel):
    email: EmailStr
    role: RestaurantRole


DemoRoleName = Literal["MANAGER", "CASHIER", "KITCHEN"]


class DemoRole(BaseModel):
    role: DemoRoleName
    label: str
    description: str


class DemoInfo(BaseModel):
    enabled: bool
    restaurant_name: str | None = None
    roles: list[DemoRole] = Field(default_factory=list)


class DemoLoginRequest(RequestModel):
    role: DemoRoleName
