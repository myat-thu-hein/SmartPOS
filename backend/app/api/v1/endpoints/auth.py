"""Authentication endpoints: login, logout, session info and password resets."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, client_ip, get_auth
from app.core.config import get_settings
from app.core.errors import RateLimited, Unauthorized
from app.core.rate_limit import login_limiter
from app.db.session import get_db
from app.models import User
from app.schemas.auth import (
    ChangePasswordRequest,
    DemoInfo,
    DemoLoginRequest,
    LoginRequest,
    LoginResponse,
    MeOut,
    PasswordResetConfirm,
    PasswordResetRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserOut,
)
from app.schemas.common import Message
from app.services import auth as auth_service
from app.services import demo as demo_service
from app.services.audit import record_audit
from app.services.users import memberships_for

router = APIRouter(prefix="/auth", tags=["auth"])


def _rate_limit(request: Request, email: str | None, scope: str) -> None:
    settings = get_settings()
    limits = [(f"{scope}:ip:{client_ip(request)}", settings.login_rate_limit_ip_attempts)]
    if email:
        limits.append((f"{scope}:email:{auth_service.normalize_email(email)}", settings.login_rate_limit_attempts))
    for key, limit in limits:
        allowed, retry_after = login_limiter.hit(key, limit, settings.login_rate_limit_window_seconds)
        if not allowed:
            raise RateLimited("Too many attempts. Please wait and try again.", details={"retry_after": retry_after})


def _login(db: Session, request: Request, data: LoginRequest) -> tuple[User, auth_service.IssuedSession]:
    _rate_limit(request, data.email, "login")
    user = auth_service.authenticate(db, data.email, data.password)
    ip = client_ip(request)
    if user is None:
        record_audit(
            db,
            action="auth.login_failed",
            actor_user_id=None,
            ip_address=ip,
            details={"email_domain": data.email.split("@")[-1]},
        )
        db.commit()
        raise Unauthorized("Invalid email or password.", code="invalid_credentials")
    issued = auth_service.create_session(db, user, ip=ip, user_agent=request.headers.get("User-Agent"))
    record_audit(db, action="auth.login", actor_user_id=user.id, ip_address=ip, entity_type="user", entity_id=user.id)
    db.commit()
    # The per-account budget is for failed attempts: signing in on a till, a phone and a
    # tablet must not use it up. The per-IP budget keeps counting every attempt.
    login_limiter.reset(f"login:email:{auth_service.normalize_email(data.email)}")
    return user, issued


def _me(db: Session, user: User) -> MeOut:
    return MeOut(user=UserOut.model_validate(user), memberships=memberships_for(db, user))


def _session_response(
    db: Session, response: Response, user: User, issued: auth_service.IssuedSession, *, remember: bool = True
) -> LoginResponse:
    settings = get_settings()
    # Without "keep me signed in" the cookies have no Max-Age, so the browser drops them on close.
    max_age = settings.session_ttl_hours * 3600 if remember else None
    common = {
        "secure": settings.secure_cookies,
        "samesite": settings.cookie_samesite,
        "domain": settings.cookie_domain,
        "path": "/",
        "max_age": max_age,
    }
    response.set_cookie(settings.session_cookie_name, issued.token, httponly=True, **common)
    # Readable by the frontend so it can echo the value in X-CSRF-Token.
    response.set_cookie(settings.csrf_cookie_name, issued.csrf_token, httponly=False, **common)
    me = _me(db, user)
    return LoginResponse(
        user=me.user, memberships=me.memberships, csrf_token=issued.csrf_token, expires_at=issued.session.expires_at
    )


@router.post("/login", response_model=LoginResponse, summary="Sign in (browser session cookie)")
def login(data: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> LoginResponse:
    user, issued = _login(db, request, data)
    return _session_response(db, response, user, issued, remember=data.remember)


@router.get("/demo", response_model=DemoInfo, summary="Whether one-click demo sign-in is available")
def demo_info(db: Session = Depends(get_db)) -> DemoInfo:
    return demo_service.info(db)


@router.post("/demo-login", response_model=LoginResponse, summary="Sign in to the demo restaurant by role")
def demo_login(
    data: DemoLoginRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> LoginResponse:
    _rate_limit(request, None, "demo-login")
    user = demo_service.account_for(db, data.role)
    ip = client_ip(request)
    issued = auth_service.create_session(db, user, ip=ip, user_agent=request.headers.get("User-Agent"))
    record_audit(
        db,
        action="auth.demo_login",
        actor_user_id=user.id,
        ip_address=ip,
        entity_type="user",
        entity_id=user.id,
        details={"role": data.role},
    )
    db.commit()
    return _session_response(db, response, user, issued)


@router.post("/token", response_model=TokenResponse, summary="Obtain a bearer token for API clients")
def token(data: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    _, issued = _login(db, request, data)
    return TokenResponse(access_token=issued.token, expires_at=issued.session.expires_at)


@router.post("/logout", response_model=Message)
def logout(response: Response, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> Message:
    settings = get_settings()
    auth_service.revoke_session(db, auth.session)
    record_audit(db, action="auth.logout", actor_user_id=auth.user.id, entity_type="user", entity_id=auth.user.id)
    db.commit()
    for name in (settings.session_cookie_name, settings.csrf_cookie_name):
        response.delete_cookie(name, path="/", domain=settings.cookie_domain)
    return Message(message="Signed out.")


@router.get("/me", response_model=MeOut)
def me(auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> MeOut:
    return _me(db, auth.user)


@router.patch("/me", response_model=MeOut)
def update_profile(
    data: UpdateProfileRequest, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)
) -> MeOut:
    demo_service.ensure_not_shared_demo_account(db, auth.user)
    for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(auth.user, field, value)
    db.commit()
    return _me(db, auth.user)


@router.post("/change-password", response_model=Message)
def change_password(
    data: ChangePasswordRequest, request: Request, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)
) -> Message:
    _rate_limit(request, auth.user.email, "change-password")
    demo_service.ensure_not_shared_demo_account(db, auth.user)
    auth_service.change_password(db, auth.user, data.current_password, data.new_password, auth.session.id)
    db.commit()
    return Message(message="Password changed. Other sessions were signed out.")


@router.post("/password-reset/request", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
def request_password_reset(data: PasswordResetRequest, request: Request, db: Session = Depends(get_db)) -> Message:
    _rate_limit(request, data.email, "password-reset")
    auth_service.request_password_reset(db, data.email, ip=client_ip(request))
    return Message(message="If an account exists for this email, a reset link has been sent.")


@router.post("/password-reset/confirm", response_model=Message)
def confirm_password_reset(data: PasswordResetConfirm, request: Request, db: Session = Depends(get_db)) -> Message:
    _rate_limit(request, None, "password-reset-confirm")
    auth_service.confirm_password_reset(db, data.token, data.new_password)
    return Message(message="Your password has been reset. You can now sign in.")
