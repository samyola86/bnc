import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.editor import ensure_editor, require_editor
from app.db.session import get_session
from app.editorial.models import Story, StoryVersion
from app.ingestion.service import audit, now
from app.publishing.models import PublishingRequest

router = APIRouter(dependencies=[Depends(require_editor)], tags=["editorial publishing queue"])
DB = Annotated[Session, Depends(get_session)]


def cancel_pending(session, story_id):
    for request in session.scalars(
        select(PublishingRequest).where(
            PublishingRequest.story_id == story_id, PublishingRequest.status != "CANCELLED"
        )
    ):
        request.status = "CANCELLED"
        request.updated_at = now()


class Submit(BaseModel):
    base_version: int = Field(ge=1)


@router.post("/stories/{story_id}/queue", status_code=201)
def submit(story_id: uuid.UUID, body: Submit, session: DB):
    story = session.scalar(select(Story).where(Story.id == story_id).with_for_update())
    if not story:
        raise HTTPException(404, "Story not found")
    if story.status not in {"DRAFT", "CHANGES_REQUESTED"}:
        raise HTTPException(409, "Only editable drafts can enter this queue")
    version = session.scalar(
        select(StoryVersion)
        .where(StoryVersion.story_id == story_id)
        .order_by(StoryVersion.version_number.desc())
        .limit(1)
    )
    if version.version_number != body.base_version:
        raise HTTPException(409, "This story changed. Reload before sending to publishing")
    content = version.content_json
    if not (
        version.title.strip()
        and content.get("body", "").strip()
        and content.get("category", "").strip()
        and content.get("tags")
        and content.get("contributors")
    ):
        raise HTTPException(422, "Add content, category, tags and contributors before publishing")
    destinations = list(dict.fromkeys(content.get("destinations", [])))
    if not destinations:
        raise HTTPException(422, "Choose at least one publishing destination")
    if "instagram" in destinations and not content.get("cover_image_id"):
        raise HTTPException(422, "Add a cover image for this Instagram feed post")
    from datetime import datetime

    scheduled = (
        datetime.fromisoformat(content["scheduled_at"]) if content.get("scheduled_at") else None
    )
    if scheduled and scheduled <= now():
        raise HTTPException(422, "Choose a future time in Dhaka or clear the schedule")
    existing = session.scalar(
        select(PublishingRequest).where(
            PublishingRequest.story_id == story_id,
            PublishingRequest.version_id == version.id,
            PublishingRequest.status != "CANCELLED",
        )
    )
    if existing:
        return {"id": str(existing.id), "status": existing.status}
    cancel_pending(session, story_id)
    request = PublishingRequest(
        story_id=story_id,
        version_id=version.id,
        destinations=destinations,
        scheduled_at=scheduled,
        status="SCHEDULED" if scheduled else "QUEUED",
    )
    session.add(request)
    session.flush()
    audit(
        session,
        "story.queued",
        story_id,
        ensure_editor(session),
        version=version.version_number,
        destinations=destinations,
        scheduled_at=scheduled.isoformat() if scheduled else None,
    )
    session.commit()
    return {"id": str(request.id), "status": request.status}


@router.get("/publishing/queue")
def queue(session: DB):
    rows = session.execute(
        select(PublishingRequest, StoryVersion, Story)
        .join(StoryVersion, PublishingRequest.version_id == StoryVersion.id)
        .join(Story, PublishingRequest.story_id == Story.id)
        .where(PublishingRequest.status != "CANCELLED")
        .order_by(PublishingRequest.created_at.desc())
        .limit(200)
    )
    return {
        "items": [
            {
                "id": str(request.id),
                "story_id": str(story.id),
                "title": version.title,
                "version": version.version_number,
                "origin_item_id": story.origin_item_id,
                "destinations": request.destinations,
                "scheduled_at": request.scheduled_at,
                "status": request.status,
                "created_at": request.created_at,
                "delivery_status": "Awaiting editorial approval and connected destinations",
            }
            for request, version, story in rows
        ]
    }


@router.post("/publishing/queue/{request_id}/cancel")
def cancel(request_id: uuid.UUID, session: DB):
    request = session.get(PublishingRequest, request_id)
    if not request:
        raise HTTPException(404, "Queue entry not found")
    session.scalar(select(Story).where(Story.id == request.story_id).with_for_update())
    request.status = "CANCELLED"
    audit(
        session,
        "story.queue_cancelled",
        request.story_id,
        ensure_editor(session),
        request_id=str(request.id),
    )
    session.commit()
    return {"status": "CANCELLED"}
