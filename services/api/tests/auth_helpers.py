from datetime import timedelta

from app.auth.editor import EDITOR_ID
from app.auth.models import LoginSession, User
from app.auth.security import digest, now, password_hash


def seed_actor(session):
    if not session.get(User, EDITOR_ID):
        session.add(
            User(
                id=EDITOR_ID,
                name="Test administrator",
                email="admin@example.test",
                username="admin",
                role="SUPERADMIN",
                active=True,
                password_hash=password_hash("test-only-password"),
            )
        )
        session.flush()
    session.info["actor_id"] = EDITOR_ID
    return EDITOR_ID


def session_cookie(factory):
    with factory() as session:
        seed_actor(session)
        session.add(
            LoginSession(
                user_id=EDITOR_ID,
                token_hash=digest("test-session-only"),
                expires_at=now() + timedelta(hours=1),
                mfa_verified=True,
            )
        )
        session.commit()
    return {"bnc_session": "test-session-only"}
