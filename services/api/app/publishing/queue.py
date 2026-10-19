import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.editor import (
    accessible_stories,
    current_user,
    ensure_editor,
    require_editor,
    story_access,
)
from app.auth.models import User
from app.db.session import get_session
from app.editorial.drafts import draft_view
from app.editorial.models import Story, StoryVersion
from app.editorial.readiness import readiness
from app.ingestion.service import audit, now
from app.publishing.models import PublishingRequest, ReviewDecision

router = APIRouter(dependencies=[Depends(require_editor)], tags=["editorial review"])
DB = Annotated[Session, Depends(get_session)]
ACTIVE = {"IN_REVIEW", "APPROVED", "READY", "QUEUED", "SCHEDULED"}


def cancel_pending(session, story_id):
    for request in session.scalars(
        select(PublishingRequest).where(
            PublishingRequest.story_id == story_id, PublishingRequest.status.in_(ACTIVE)
        )
    ):
        request.status = "CANCELLED"
        session.add(
            ReviewDecision(
                created_at=now(),
                request_id=request.id,
                actor_id=ensure_editor(session),
                decision="INVALIDATED",
                notes="New revision saved",
            )
        )


class Submit(BaseModel):
    base_version: int = Field(ge=1)


def latest(session, story_id):
    return session.scalar(
        select(StoryVersion)
        .where(StoryVersion.story_id == story_id)
        .order_by(StoryVersion.version_number.desc())
        .limit(1)
    )


def validate(session, story, version):
    draft = draft_view(session, story.id, version.id)
    result = readiness(version.content_json, version.title, draft["language"], draft["credits"])
    if result["errors"]:
        raise HTTPException(
            422, {"message": "Complete the publishing requirements", "fields": result["errors"]}
        )
    return draft


@router.get("/stories/{story_id}/readiness")
def check_readiness(story_id: uuid.UUID, session: DB):
    story = story_access(session, session.get(Story, story_id))
    version = latest(session, story.id)
    draft = draft_view(session, story.id)
    return readiness(version.content_json, version.title, draft["language"], draft["credits"])


@router.post("/stories/{story_id}/queue", status_code=201)
@router.post("/stories/{story_id}/submit-review", status_code=201)
def submit(story_id: uuid.UUID, body: Submit, session: DB):
    story = story_access(
        session, session.scalar(select(Story).where(Story.id == story_id).with_for_update())
    )
    version = latest(session, story_id)
    if version.version_number != body.base_version:
        raise HTTPException(409, "This story changed. Reload before submitting")
    existing = session.scalar(
        select(PublishingRequest).where(
            PublishingRequest.story_id == story_id,
            PublishingRequest.version_id == version.id,
            PublishingRequest.status.in_({"IN_REVIEW", "APPROVED", "READY"}),
        )
    )
    if existing:
        return {"id": str(existing.id), "status": existing.status}
    if story.status not in {"DRAFT", "CHANGES_REQUESTED"}:
        raise HTTPException(409, "Only a draft can be submitted for review")
    if current_user(session).role == "CONTENT_WRITER" and version.content_json.get("scheduled_at"):
        raise HTTPException(403, "Only Editors and Superadmins can request publication schedules")
    validate(session, story, version)
    cancel_pending(session, story_id)
    request = PublishingRequest(
        story_id=story_id,
        version_id=version.id,
        destinations=version.content_json["destinations"],
        scheduled_at=version.content_json.get("scheduled_at"),
        status="IN_REVIEW",
        submitter_id=ensure_editor(session),
    )
    if request.scheduled_at:
        from datetime import datetime

        request.scheduled_at = datetime.fromisoformat(request.scheduled_at)
    session.add(request)
    session.flush()
    story.status = "IN_REVIEW"
    session.add(
        ReviewDecision(
            created_at=now(),
            request_id=request.id,
            actor_id=ensure_editor(session),
            decision="SUBMITTED",
        )
    )
    audit(
        session,
        "story.submitted",
        story.id,
        ensure_editor(session),
        request_id=str(request.id),
        version=version.version_number,
    )
    session.commit()
    return {"id": str(request.id), "status": request.status}


def request_view(session, request, story, version):
    submitter = session.get(User, request.submitter_id) if request.submitter_id else None
    reviewer = session.get(User, request.reviewer_id) if request.reviewer_id else None
    draft = draft_view(session, story.id, version.id)
    return {
        "id": str(request.id),
        "story_id": str(story.id),
        "title": version.title,
        "version": version.version_number,
        "version_id": str(version.id),
        "origin_item_id": story.origin_item_id,
        "destinations": request.destinations,
        "scheduled_at": request.scheduled_at,
        "status": request.status,
        "created_at": request.created_at,
        "submitter": submitter.name if submitter else "Legacy preparation",
        "submitter_id": request.submitter_id,
        "reviewer": reviewer.name if reviewer else None,
        "decided_at": request.decided_at,
        "review_notes": request.review_notes,
        "contributors": draft.get("contributors", []),
        "format": draft.get("format", "article"),
        "warnings": draft["warnings"],
        "delivery_status": "External delivery is not enabled",
    }


@router.get("/publishing/queue")
def queue(session: DB, status: str = "IN_REVIEW"):
    statement = (
        select(PublishingRequest, StoryVersion, Story)
        .join(StoryVersion, PublishingRequest.version_id == StoryVersion.id)
        .join(Story, PublishingRequest.story_id == Story.id)
        .where(accessible_stories(session))
        .order_by(PublishingRequest.created_at.desc())
        .limit(200)
    )
    if status != "all":
        statement = statement.where(PublishingRequest.status == status)
    return {
        "items": [
            request_view(session, request, story, version)
            for request, version, story in session.execute(statement)
        ]
    }


def get_request(session, request_id, *, lock=False):
    request = session.get(PublishingRequest, request_id)
    if not request:
        raise HTTPException(404, "Submission not found")
    statement = select(Story).where(Story.id == request.story_id)
    story = story_access(
        session, session.scalar(statement.with_for_update() if lock else statement)
    )
    session.refresh(request)  # Re-read after acquiring the story's transition lock.
    return request, story, session.get(StoryVersion, request.version_id)


@router.get("/publishing/requests/{request_id}")
def detail(request_id: uuid.UUID, session: DB):
    request, story, version = get_request(session, request_id)
    history = session.scalars(
        select(ReviewDecision)
        .where(ReviewDecision.request_id == request.id)
        .order_by(ReviewDecision.created_at, ReviewDecision.id)
    )
    return {
        "request": request_view(session, request, story, version),
        "draft": draft_view(session, story.id, version.id),
        "history": [
            {
                "decision": row.decision,
                "notes": row.notes,
                "actor": session.get(User, row.actor_id).name,
                "created_at": row.created_at,
                "self_approval_override": row.self_approval_override,
            }
            for row in history
        ],
    }


class Decision(BaseModel):
    request_id: uuid.UUID
    base_version: int = Field(ge=1)
    notes: str = Field(default="", max_length=5000)
    self_approval_override: bool = False


def decide(session, story_id, body, outcome):
    actor = current_user(session)
    if actor.role not in {"SUPERADMIN", "EDITOR"}:
        raise HTTPException(403, "Only Editors and Superadmins may review or authorize delivery")
    request, story, version = get_request(session, body.request_id, lock=True)
    if (
        story.id != story_id
        or version.version_number != body.base_version
        or latest(session, story.id).id != version.id
    ):
        raise HTTPException(409, "Submission or revision changed. Reload before deciding")
    expected = "APPROVED" if outcome == "READY" else "IN_REVIEW"
    if request.status != expected or story.status != expected:
        raise HTTPException(409, "This submission no longer accepts that decision")
    if outcome in {"CHANGES_REQUESTED", "REJECTED"} and not body.notes.strip():
        raise HTTPException(422, "Give an editorial reason for this decision")
    own = actor.id in {story.author_id, version.editor_id, request.submitter_id}
    override = own and outcome in {"APPROVED", "READY"}
    if override and not (
        actor.role == "SUPERADMIN" and body.self_approval_override and body.notes.strip()
    ):
        raise HTTPException(
            403, "Self-approval requires an explicit Superadmin exception with a reason"
        )
    if outcome in {"APPROVED", "READY"}:
        validate(session, story, version)
    request.status, request.reviewer_id = outcome, actor.id
    request.decided_at, request.review_notes = now(), body.notes.strip()
    story.status = "CHANGES_REQUESTED" if outcome == "REJECTED" else outcome
    session.add(
        ReviewDecision(
            created_at=now(),
            request_id=request.id,
            actor_id=actor.id,
            decision=outcome,
            notes=body.notes.strip(),
            self_approval_override=override,
        )
    )
    audit(
        session,
        "story." + outcome.lower(),
        story.id,
        actor.id,
        request_id=str(request.id),
        version_id=str(version.id),
        self_approval_override=override,
        notes=body.notes.strip(),
    )
    if outcome == "APPROVED":
        from app.tasks.models import NewsroomTask

        for task in session.scalars(
            select(NewsroomTask).where(
                NewsroomTask.story_id == story.id, NewsroomTask.status == "IN_REVIEW"
            )
        ):
            task.status, task.completed_at = "COMPLETED", now()
            audit(session, "task.completed_by_approval", task.id, actor.id)
    session.commit()
    return {"status": outcome, "version_id": str(version.id)}


@router.post("/stories/{story_id}/approve")
def approve(story_id: uuid.UUID, body: Decision, session: DB):
    return decide(session, story_id, body, "APPROVED")


@router.post("/stories/{story_id}/request-changes")
def changes(story_id: uuid.UUID, body: Decision, session: DB):
    return decide(session, story_id, body, "CHANGES_REQUESTED")


@router.post("/stories/{story_id}/reject")
def reject(story_id: uuid.UUID, body: Decision, session: DB):
    return decide(session, story_id, body, "REJECTED")


@router.post("/stories/{story_id}/ready")
def ready(story_id: uuid.UUID, body: Decision, session: DB):
    return decide(session, story_id, body, "READY")


@router.post("/publishing/queue/{request_id}/cancel")
def withdraw(request_id: uuid.UUID, session: DB):
    request, story, version = get_request(session, request_id, lock=True)
    if request.status not in ACTIVE:
        raise HTTPException(409, "This submission is already closed")
    if current_user(session).role == "CONTENT_WRITER" and request.status != "IN_REVIEW":
        raise HTTPException(403, "Writers can withdraw pending submissions only")
    request.status = "WITHDRAWN"
    if latest(session, story.id).id == version.id:
        story.status = "DRAFT"
    session.add(
        ReviewDecision(
            created_at=now(),
            request_id=request.id,
            actor_id=ensure_editor(session),
            decision="WITHDRAWN",
        )
    )
    audit(session, "story.withdrawn", story.id, ensure_editor(session), request_id=str(request.id))
    session.commit()
    return {"status": "WITHDRAWN"}
