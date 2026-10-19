"""Editor service credential for the localhost dashboard; never sent to the browser.

Per-user sessions/MFA remain a separate deployment concern. This credential grants
only the source, ingestion, and candidate-draft routes using this dependency.
"""

import secrets
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.models import User
from app.config import get_settings
from app.db.session import get_session

EDITOR_ID = uuid.UUID("3151c161-5adb-4d84-a450-7319a9b9c62b")
bearer = HTTPBearer(auto_error=False)


def require_editor(
    credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[Session, Depends(get_session)],
) -> uuid.UUID:
    token = get_settings().ingestion_api_token
    if not token or not credential or not secrets.compare_digest(credential.credentials, token):
        raise HTTPException(401, "An editor credential is required")
    user = session.get(User, EDITOR_ID)
    if user and (
        not user.active or user.role not in {"editor", "administrator", "editor_in_chief"}
    ):
        raise HTTPException(403, "An active editor role is required")
    return EDITOR_ID


def ensure_editor(session: Session) -> uuid.UUID:
    if not session.get(User, EDITOR_ID):
        session.add(
            User(
                id=EDITOR_ID,
                email="local-source-editor@bnc.invalid",
                name="Local source editor",
                role="editor",
                active=True,
            )
        )
        session.flush()
    return EDITOR_ID
