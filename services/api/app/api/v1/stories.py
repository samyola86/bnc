import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.models import AIJob
from app.ai.schemas import GenerateInput
from app.ai.service import expire_job, job_view, request_job
from app.ai.tasks import enqueue
from app.auth.editor import ensure_editor, require_editor
from app.db.session import get_session
from app.editorial.drafts import draft_view
from app.editorial.models import Story, StorySource, StoryVersion
from app.ingestion.candidates import cursor_offset, next_cursor
from app.ingestion.policy import collection_settings
from app.ingestion.schemas import DraftInput
from app.ingestion.service import audit

router = APIRouter(dependencies=[Depends(require_editor)], tags=["stories and AI"])
DB = Annotated[Session, Depends(get_session)]


class ManualInput(DraftInput):
    base_version: int = 1
    language: Literal["bn", "en"] = "bn"


@router.post("/stories", status_code=201)
def create_story(body: ManualInput, session: DB):
    if body.ai_job_id:
        raise HTTPException(422, "Create the story before requesting an AI preview")
    actor = ensure_editor(session)
    if "language" not in body.model_fields_set:
        body.language = collection_settings(session).draft_language
    story = Story(language=body.language, status="DRAFT", author_id=actor, type=body.format)
    session.add(story)
    session.flush()
    version = StoryVersion(
        story_id=story.id,
        version_number=1,
        editor_id=actor,
        title=body.title,
        content_json=body.model_dump(
            mode="json",
            include={
                "summary",
                "body",
                "category",
                "tags",
                "social_captions",
                "language",
                "format",
                "contributors",
                "cover_image_id",
                "image_alt",
                "image_caption",
                "reporting_notes",
                "destinations",
                "social_caption",
                "scheduled_at",
            },
        ),
    )
    session.add(version)
    session.flush()
    from app.ingestion.models import Source

    for credit in body.credits:
        if credit.source_id and not session.get(Source, credit.source_id):
            raise HTTPException(422, "A referenced source no longer exists")
        session.add(
            StorySource(
                story_id=story.id,
                version_id=version.id,
                **credit.model_dump(),
                entry_method="manual",
                last_edited_by=actor,
            )
        )
    audit(session, "story.created", story.id, actor, version=1, origin="manual")
    session.commit()
    return draft_view(session, story.id)


@router.get("/stories")
def stories(
    session: DB,
    origin: str = Query("manual", pattern="^(manual|candidate|all)$"),
    cursor: str | None = Query(None, max_length=100),
):
    criteria = []
    if origin != "all":
        criteria = [
            Story.origin_item_id.is_(None)
            if origin == "manual"
            else Story.origin_item_id.is_not(None)
        ]
    offset, limit = cursor_offset(cursor), 30
    total = session.scalar(select(func.count()).select_from(Story).where(*criteria))
    rows = session.scalars(
        select(Story)
        .where(*criteria)
        .order_by(Story.updated_at.desc(), Story.id)
        .offset(offset)
        .limit(limit)
    )
    items = []
    for story in rows:
        draft = draft_view(session, story.id)
        items.append(
            {
                key: draft[key]
                for key in (
                    "id",
                    "origin_item_id",
                    "title",
                    "summary",
                    "version",
                    "status",
                    "language",
                    "warnings",
                )
            }
            | {"updated_at": story.updated_at}
        )
    return {"items": items, "total": total, "next_cursor": next_cursor(offset, limit, total)}


@router.get("/stories/{story_id}/versions")
def versions(story_id: uuid.UUID, session: DB, cursor: str | None = Query(None, max_length=100)):
    draft_view(session, story_id)
    offset, limit = cursor_offset(cursor), 30
    total = session.scalar(
        select(func.count()).select_from(StoryVersion).where(StoryVersion.story_id == story_id)
    )
    rows = session.scalars(
        select(StoryVersion)
        .where(StoryVersion.story_id == story_id)
        .order_by(StoryVersion.version_number.desc())
        .offset(offset)
        .limit(limit)
    )
    return {
        "items": [
            {
                "version": row.version_number,
                "title": row.title,
                "created_at": row.created_at,
                "content": row.content_json,
            }
            for row in rows
        ],
        "total": total,
        "next_cursor": next_cursor(offset, limit, total),
    }


@router.post("/stories/{story_id}/ai-draft", status_code=202)
def generate_story(story_id: uuid.UUID, body: GenerateInput, session: DB):
    job = request_job(session, story_id, body)
    if not enqueue(job.id):
        raise HTTPException(
            503, "AI queue unavailable. Check Redis and the worker; your writing is unchanged"
        )
    return {"job_id": str(job.id), "status": "PENDING"}


@router.get("/stories/{story_id}/ai-jobs")
def story_jobs(story_id: uuid.UUID, session: DB):
    draft_view(session, story_id)
    jobs = session.scalars(
        select(AIJob).where(AIJob.story_id == story_id).order_by(AIJob.created_at.desc()).limit(10)
    ).all()
    for job in jobs:
        expire_job(job)
    session.commit()
    return {"items": [job_view(job) for job in jobs]}


@router.get("/ai/jobs/{job_id}")
def ai_job(job_id: uuid.UUID, session: DB):
    job = session.get(AIJob, job_id)
    if not job:
        raise HTTPException(404, "AI job not found")
    expire_job(job)
    session.commit()
    return job_view(job)
