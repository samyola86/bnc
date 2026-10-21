import secrets
import smtplib
import ssl
import time
import uuid
from datetime import timedelta
from email.message import EmailMessage
from typing import Annotated, Literal

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.editor import ensure_editor, require_superadmin
from app.auth.models import ResetToken, User
from app.auth.security import (
    COOKIE,
    aware,
    cipher,
    consume_attempt,
    cookie_secure,
    csrf,
    current_session,
    digest,
    hasher,
    issue_session,
    now,
    password_hash,
    revoke,
    user_view,
    verify,
)
from app.config import get_settings
from app.db.session import get_session
from app.editorial.models import AuditEvent
from app.ingestion.service import audit

router = APIRouter(tags=["individual authentication"])
admin = APIRouter(
    prefix="/admin", dependencies=[Depends(require_superadmin)], tags=["administration"]
)
DB = Annotated[Session, Depends(get_session)]
Role = Literal["SUPERADMIN", "EDITOR", "CONTENT_WRITER"]


class Login(BaseModel):
    identity: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=256)


@router.post("/auth/login")
def login(body: Login, request: Request, response: Response, session: DB):
    csrf(request)
    consume_attempt(session, "login-ip:" + request.client.host, 60)
    identity = body.identity.strip().lower()
    consume_attempt(session, "login-account:" + identity)
    user = session.scalar(
        select(User).where(or_(User.email == identity, User.username == identity))
    )
    valid = verify(body.password, user.password_hash if user else None)
    if not valid or not user.active or user.deleted_at:
        audit(session, "auth.login_failed", uuid.UUID(int=0))
        session.commit()
        raise HTTPException(401, "Invalid credentials or unavailable account")
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = password_hash(body.password)
    old = request.cookies.get(COOKIE)
    if old:
        from app.auth.models import LoginSession

        previous = session.scalar(
            select(LoginSession).where(LoginSession.token_hash == digest(old))
        )
        if previous:
            previous.revoked = True
    login = issue_session(session, user, response, request=request)
    user.last_login = now()
    audit(session, "auth.password_verified", user.id, user.id)
    session.commit()
    return {"user": user_view(user), "mfa_required": not login.mfa_verified}


@router.get("/auth/me")
def me(request: Request, session: DB):
    login, user = current_session(request, session, pending=True)
    return {"user": user_view(user), "mfa_required": not login.mfa_verified}


@router.post("/auth/logout")
def logout(request: Request, response: Response, session: DB):
    login, user = current_session(request, session, pending=True)
    login.revoked = True
    response.delete_cookie(
        COOKIE, path="/", secure=cookie_secure(request), httponly=True, samesite="strict"
    )
    audit(session, "auth.logout", user.id, user.id)
    session.commit()
    return {"ok": True}


@router.post("/auth/logout-all")
def logout_all(request: Request, response: Response, session: DB):
    _, user = current_session(request, session)
    revoke(session, user.id)
    response.delete_cookie(
        COOKIE, path="/", secure=cookie_secure(request), httponly=True, samesite="strict"
    )
    audit(session, "auth.logout_all", user.id, user.id)
    session.commit()
    return {"ok": True}


@router.post("/auth/renew")
def renew(request: Request, response: Response, session: DB):
    old, user = current_session(request, session)
    old.revoked = True
    issue_session(session, user, response, verified=True, request=request)
    session.commit()
    return {"ok": True}


class Code(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


@router.post("/auth/mfa/setup")
def mfa_setup(request: Request, session: DB):
    _, user = current_session(request, session, pending=True)
    if user.mfa_enabled:
        raise HTTPException(409, "MFA is already enrolled")
    secret = pyotp.random_base32()
    user.mfa_secret = cipher().encrypt(secret.encode()).decode()
    session.commit()
    return {"uri": pyotp.TOTP(secret).provisioning_uri(user.email, issuer_name="BNC Newsroom")}


@router.post("/auth/mfa/verify")
def mfa_verify(body: Code, request: Request, response: Response, session: DB):
    old, user = current_session(request, session, pending=True)
    consume_attempt(session, "mfa:" + str(user.id), 6)
    user = session.scalar(select(User).where(User.id == user.id).with_for_update())
    if not user.mfa_secret:
        raise HTTPException(422, "Enroll an authenticator first")
    secret = cipher().decrypt(user.mfa_secret.encode()).decode()
    step = int(time.time() // 30)
    if step <= user.mfa_last_step or not pyotp.TOTP(secret).verify(body.code):
        raise HTTPException(401, "Invalid or already used authenticator code")
    user.mfa_last_step, user.mfa_enabled = step, True
    revoke(session, user.id)
    issue_session(session, user, response, verified=True, request=request)
    audit(session, "auth.mfa_verified", user.id, user.id)
    session.commit()
    return {"ok": True}


def send_reset(user, token):
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from:
        raise HTTPException(503, "Configure SMTP to deliver password resets")
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = (
        settings.smtp_from,
        user.email,
        "BNC password reset",
    )
    message.set_content(
        "Reset your password within 30 minutes:\n"
        f"{settings.auth_origin}/reset-password#token={token}\n"
    )
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as mail:
            mail.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                mail.login(settings.smtp_username, settings.smtp_password)
            mail.send_message(message)
    except (OSError, smtplib.SMTPException):
        raise HTTPException(503, "Password reset delivery unavailable") from None


def initiate_reset(session, user, actor=None):
    token = secrets.token_urlsafe(48)
    send_reset(user, token)
    revoke(session, user.id)
    session.add(
        ResetToken(
            user_id=user.id, token_hash=digest(token), expires_at=now() + timedelta(minutes=30)
        )
    )
    audit(session, "auth.reset_requested", user.id, actor)
    session.commit()


class ResetRequest(BaseModel):
    identity: str = Field(min_length=1, max_length=320)


@router.post("/auth/forgot-password")
def forgot(body: ResetRequest, request: Request, session: DB):
    csrf(request)
    consume_attempt(session, "reset-ip:" + request.client.host, 10)
    consume_attempt(session, "reset-user:" + body.identity.strip().lower(), 3)
    identity = body.identity.strip().lower()
    user = session.scalar(
        select(User).where(or_(User.email == identity, User.username == identity))
    )
    if user and user.active and not user.deleted_at:
        try:
            initiate_reset(session, user)
        except HTTPException:
            session.rollback()
    return {"message": "If the account is eligible, a reset email will be sent"}


class ResetPassword(BaseModel):
    token: str = Field(min_length=20, max_length=128)
    password: str = Field(min_length=12, max_length=256)


@router.post("/auth/reset-password")
def reset_password(body: ResetPassword, request: Request, session: DB):
    csrf(request)
    consume_attempt(session, "reset-consume:" + request.client.host, 20)
    token = session.scalar(
        select(ResetToken).where(ResetToken.token_hash == digest(body.token)).with_for_update()
    )
    if not token or token.used or aware(token.expires_at) <= now():
        raise HTTPException(422, "Invalid or expired reset token")
    user = session.get(User, token.user_id)
    if not user.active or user.deleted_at:
        raise HTTPException(422, "Account unavailable")
    user.password_hash = password_hash(body.password)
    revoke(session, user.id)
    audit(session, "auth.password_reset", user.id, user.id)
    session.commit()
    return {"ok": True}


class Account(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    username: str = Field(pattern=r"^[a-zA-Z0-9_.-]{3,80}$")
    role: Role

    @field_validator("email", "username")
    @classmethod
    def lowercase(cls, value):
        return value.lower()

    @field_validator("name")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Name is required")
        return value.strip()


class NewAccount(Account):
    password: str = Field(min_length=12, max_length=256)


def account_commit(session):
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "Email or username already exists") from None


@admin.get("/users")
def users(session: DB, query: str = "", role: Role | None = None, status: str = "all"):
    statement = select(User).order_by(User.name).limit(200)
    if query:
        pattern = f"%{query[:200]}%"
        statement = statement.where(
            or_(User.name.ilike(pattern), User.email.ilike(pattern), User.username.ilike(pattern))
        )
    if role:
        statement = statement.where(User.role == role)
    if status == "active":
        statement = statement.where(User.active.is_(True), User.deleted_at.is_(None))
    elif status == "suspended":
        statement = statement.where(User.active.is_(False), User.deleted_at.is_(None))
    elif status == "deleted":
        statement = statement.where(User.deleted_at.is_not(None))
    return {"items": [user_view(user) for user in session.scalars(statement)]}


@admin.post("/users", status_code=201)
def create_user(body: NewAccount, session: DB):
    user = User(**body.model_dump(exclude={"password"}), password_hash=password_hash(body.password))
    session.add(user)
    try:
        session.flush()
    except IntegrityError:
        raise HTTPException(409, "Email or username already exists") from None
    audit(session, "user.created", user.id, ensure_editor(session), role=user.role)
    account_commit(session)
    return user_view(user)


def lock_account(session, user_id):
    # Serialize the active-superadmin set before locking any target account.
    admins = session.scalars(
        select(User)
        .where(User.role == "SUPERADMIN", User.active.is_(True), User.deleted_at.is_(None))
        .order_by(User.id)
        .with_for_update()
    ).all()
    user = session.scalar(select(User).where(User.id == user_id).with_for_update())
    if not user:
        raise HTTPException(404, "Account not found")
    return user, admins


@admin.patch("/users/{user_id}")
def edit_user(user_id: uuid.UUID, body: Account, session: DB):
    user, admins = lock_account(session, user_id)
    if user.deleted_at:
        raise HTTPException(409, "Deleted accounts cannot be edited")
    if user.role == "SUPERADMIN" and body.role != "SUPERADMIN":
        if len(admins) <= 1 or user.id == ensure_editor(session):
            raise HTTPException(409, "Cannot demote the last Superadmin or your own account")
    security_change = any(
        getattr(user, key) != getattr(body, key) for key in ("role", "email", "username")
    )
    for key, value in body.model_dump().items():
        setattr(user, key, value)
    if security_change:
        revoke(session, user.id)
    audit(session, "user.updated", user.id, ensure_editor(session), role=user.role)
    account_commit(session)
    return user_view(user)


class Status(BaseModel):
    status: Literal["active", "suspended", "deleted"]


@admin.post("/users/{user_id}/status")
def status_user(user_id: uuid.UUID, body: Status, session: DB):
    user, admins = lock_account(session, user_id)
    if user.deleted_at:
        raise HTTPException(409, "Deleted accounts cannot be reactivated")
    if body.status != "active" and (
        user.id == ensure_editor(session)
        or (user.role == "SUPERADMIN" and user.active and len(admins) <= 1)
    ):
        raise HTTPException(409, "Cannot disable your own account or the last active Superadmin")
    user.active = body.status == "active"
    if body.status == "deleted":
        user.deleted_at = now()
    revoke(session, user.id)
    audit(session, "user." + body.status, user.id, ensure_editor(session))
    session.commit()
    return user_view(user)


@admin.post("/users/{user_id}/reset-password")
def admin_reset(user_id: uuid.UUID, session: DB):
    user = session.get(User, user_id)
    if not user or user.deleted_at or not user.active:
        raise HTTPException(422, "Account is not eligible for reset")
    initiate_reset(session, user, ensure_editor(session))
    return {"message": "Reset email sent; previous sessions revoked"}


@admin.get("/audit")
def audit_log(session: DB, user_id: uuid.UUID | None = None):
    statement = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(200)
    if user_id:
        statement = statement.where(
            or_(AuditEvent.actor_id == user_id, AuditEvent.resource_id == user_id)
        )
    return {
        "items": [
            {
                "id": event.id,
                "actor_id": event.actor_id,
                "action": event.action,
                "resource_id": event.resource_id,
                "created_at": event.created_at,
                "details": event.event_details,
            }
            for event in session.scalars(statement)
        ]
    }


@admin.get("/system-status")
def system_status():
    settings = get_settings()
    return {
        "superadmin_mfa_required": True,
        "editor_mfa_required": settings.auth_require_editor_mfa,
        "session_hours": settings.auth_session_hours,
        "secure_cookies": settings.auth_cookie_secure,
        "origin": settings.auth_origin,
        "mfa_key_configured": bool(settings.auth_encryption_key),
        "password_reset_delivery_configured": bool(settings.smtp_host and settings.smtp_from),
        "ai_configured": bool(settings.openai_api_key and settings.openai_model),
        "ai_model": settings.openai_model or None,
        "external_delivery_enabled": False,
    }
