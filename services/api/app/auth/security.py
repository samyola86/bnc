import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import case, select, update

from app.auth.models import AuthAttempt, LoginSession, ResetToken, User
from app.config import get_settings

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))
COOKIE = "bnc_session"


def now():
    return datetime.now(UTC)


def aware(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password):
    if not 12 <= len(password) <= 256:
        raise HTTPException(422, "Passwords must contain 12–256 characters")
    return hasher.hash(password)


def verify(password, encoded):
    try:
        return hasher.verify(encoded or DUMMY_HASH, password) and bool(encoded)
    except (VerificationError, InvalidHashError):
        return False


def cipher():
    try:
        return Fernet(get_settings().auth_encryption_key.encode())
    except (ValueError, TypeError):
        raise HTTPException(503, "Configure AUTH_ENCRYPTION_KEY before enrolling MFA") from None


def consume_attempt(session, key, limit=10):
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
    cutoff = now() - timedelta(minutes=15)
    statement = insert(AuthAttempt).values(key=digest(key), attempts=1, window_start=now())
    statement = statement.on_conflict_do_update(
        index_elements=[AuthAttempt.key],
        set_={
            "attempts": case(
                (AuthAttempt.window_start < cutoff, 1), else_=AuthAttempt.attempts + 1
            ),
            "window_start": case(
                (AuthAttempt.window_start < cutoff, now()), else_=AuthAttempt.window_start
            ),
        },
    ).returning(AuthAttempt.attempts)
    attempts = session.scalar(statement)
    session.commit()
    if attempts > limit:
        raise HTTPException(429, "Too many attempts. Try again in 15 minutes")


def csrf(request):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("origin") != get_settings().auth_origin:
            raise HTTPException(403, "A trusted same-origin request is required")


def current_session(request, session, *, pending=False):
    csrf(request)
    if request.headers.get("authorization"):
        raise HTTPException(401, "Use an individual account session")
    token = request.cookies.get(COOKIE, "")
    login = session.scalar(select(LoginSession).where(LoginSession.token_hash == digest(token)))
    user = session.get(User, login.user_id) if login else None
    if (
        not login
        or login.revoked
        or aware(login.expires_at) <= now()
        or not user
        or not user.active
        or user.deleted_at
        or user.role not in {"SUPERADMIN", "EDITOR", "CONTENT_WRITER"}
    ):
        raise HTTPException(401, "Sign in to continue")
    required = (
        user.role == "SUPERADMIN"
        or (user.role == "EDITOR" and get_settings().auth_require_editor_mfa)
        or user.mfa_enabled
    )
    if required and not login.mfa_verified and not pending:
        raise HTTPException(403, "Complete MFA verification before accessing the newsroom")
    return login, user


def issue_session(session, user, response, verified=False):
    required = (
        user.role == "SUPERADMIN"
        or user.mfa_enabled
        or (user.role == "EDITOR" and get_settings().auth_require_editor_mfa)
    )
    full = verified or not required
    token = secrets.token_urlsafe(48)
    ttl = get_settings().auth_session_hours * 3600 if full else 600
    login = LoginSession(
        user_id=user.id,
        token_hash=digest(token),
        expires_at=now() + timedelta(seconds=ttl),
        mfa_verified=full,
    )
    session.add(login)
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=get_settings().auth_cookie_secure,
        samesite="strict",
        path="/",
        max_age=ttl,
    )
    return login


def revoke(session, user_id):
    session.execute(
        update(LoginSession).where(LoginSession.user_id == user_id).values(revoked=True)
    )
    session.execute(update(ResetToken).where(ResetToken.user_id == user_id).values(used=True))


def user_view(user):
    return {
        "id": str(user.id),
        "name": user.name,
        "email": user.email,
        "username": user.username,
        "role": user.role,
        "active": user.active,
        "deleted_at": user.deleted_at,
        "last_login": user.last_login,
        "created_at": user.created_at,
        "mfa_enabled": user.mfa_enabled,
        "status": "Deleted" if user.deleted_at else "Active" if user.active else "Suspended",
    }
