"""Reusable session authorization; legacy bearer credentials are never accepted."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.db.session import get_session

EDITOR_ID = uuid.UUID("3151c161-5adb-4d84-a450-7319a9b9c62b")  # Historical identity only.


def require_editor(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> uuid.UUID:
    from app.auth.security import current_session

    login, user = current_session(request, session)
    session.info["actor_id"] = user.id
    session.info["login_id"] = login.id
    return user.id


def ensure_editor(session: Session) -> uuid.UUID:
    actor = session.info.get("actor_id")
    if not actor:
        raise HTTPException(401, "Sign in to continue")
    return actor


def current_user(session):
    user = session.get(User, ensure_editor(session))
    if not user or not user.active or user.deleted_at:
        raise HTTPException(401, "Account unavailable")
    return user


def require_superadmin(
    actor: Annotated[uuid.UUID, Depends(require_editor)],
    session: Annotated[Session, Depends(get_session)],
):
    if current_user(session).role != "SUPERADMIN":
        raise HTTPException(403, "Superadmin access required")
    return actor


def require_reviewer(
    actor: Annotated[uuid.UUID, Depends(require_editor)],
    session: Annotated[Session, Depends(get_session)],
):
    if current_user(session).role not in {"SUPERADMIN", "EDITOR"}:
        raise HTTPException(403, "Editorial reviewer access required")
    return actor


def accessible_stories(session):
    from app.editorial.models import Story
    from app.tasks.models import NewsroomTask

    user = current_user(session)
    if user.role != "CONTENT_WRITER":
        return True
    return or_(
        Story.author_id == user.id,
        Story.id.in_(select(NewsroomTask.story_id).where(NewsroomTask.assignee_id == user.id)),
    )


def story_access(session, story, *, write=False):
    from app.editorial.models import Story

    if not story:
        raise HTTPException(404, "Story not found")
    allowed = session.scalar(
        select(Story.id).where(Story.id == story.id, accessible_stories(session))
    )
    if not allowed:
        raise HTTPException(403, "This story is not owned by or assigned to you")
    if write and story.status == "IN_REVIEW":
        raise HTTPException(409, "Withdraw the submitted revision before editing")
    return story
