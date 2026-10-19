import uuid

from fastapi import HTTPException
from sqlalchemy import select

from app.auth.editor import ensure_editor
from app.editorial.models import Story, StorySource, StoryVersion
from app.ingestion.candidates import attribution_rows
from app.ingestion.models import IngestedItem, Source
from app.ingestion.schemas import DraftInput
from app.ingestion.service import audit, now


def credit_warning(credits: list[dict]) -> list[str]:
    if not any(
        c.get("is_original_reporting")
        or c.get("publisher_name", "").strip()
        or c.get("attribution_text", "").strip()
        for c in credits
    ):
        return ["Missing source credit"]
    if any(
        not c.get("is_original_reporting")
        and not c.get("publisher_name", "").strip()
        and not c.get("attribution_text", "").strip()
        for c in credits
    ):
        return ["Attribution needs review"]
    return []


def draft_view(session, story_id: uuid.UUID):
    story = session.get(Story, story_id)
    if not story:
        raise HTTPException(404, "Draft not found")
    version = session.scalar(
        select(StoryVersion)
        .where(StoryVersion.story_id == story.id)
        .order_by(StoryVersion.version_number.desc())
        .limit(1)
    )
    rows = session.scalars(
        select(StorySource)
        .where(StorySource.version_id == version.id)
        .order_by(StorySource.created_at, StorySource.id)
    ).all()
    credits = [
        {
            "source_id": str(c.source_id) if c.source_id else None,
            "publisher_name": c.publisher_name,
            "original_url": c.original_url,
            "attribution_text": c.attribution_text,
            "rights_status": c.rights_status,
            "is_original_reporting": c.is_original_reporting,
            "entry_method": c.entry_method,
        }
        for c in rows
    ]
    return {
        "id": str(story.id),
        "origin_item_id": str(story.origin_item_id) if story.origin_item_id else None,
        "title": version.title,
        "version": version.version_number,
        "status": story.status,
        "language": story.language,
        **version.content_json,
        "credits": credits,
        "warnings": credit_warning(credits),
        "attribution_blocks_publishing": False,
        "provenance": attribution_rows(session, story.origin_item_id)
        if story.origin_item_id
        else [],
    }


def create_draft(session, item_id):
    item = session.scalar(select(IngestedItem).where(IngestedItem.id == item_id).with_for_update())
    if not item:
        raise HTTPException(404, "Candidate not found")
    existing = session.scalar(select(Story).where(Story.origin_item_id == item.id))
    if existing:
        return draft_view(session, existing.id)
    actor = ensure_editor(session)
    story = Story(origin_item_id=item.id, language=item.language, status="DRAFT", author_id=actor)
    session.add(story)
    session.flush()
    # Feed text is evidence, not a BNC article. The editor writes an original body.
    version = StoryVersion(
        story_id=story.id,
        version_number=1,
        editor_id=actor,
        title=item.title,
        content_json={"summary": item.excerpt, "body": "", "category": item.category},
    )
    session.add(version)
    session.flush()
    seen = set()
    for credit in attribution_rows(session, item.id):
        key = (credit["publisher_name"], credit["original_url"])
        if key in seen:
            continue
        seen.add(key)
        session.add(
            StorySource(
                story_id=story.id,
                version_id=version.id,
                source_id=uuid.UUID(credit["source_id"]),
                ingested_item_id=item.id,
                publisher_name=credit["publisher_name"],
                original_url=credit["original_url"],
                rights_status=credit["rights_status"],
                entry_method="auto",
                last_edited_by=actor,
            )
        )
    item.editorial_status = "DRAFT"
    audit(session, "candidate.draft_created", story.id, actor, item_id=str(item.id), version=1)
    session.commit()
    return draft_view(session, story.id)


def update_draft(session, story_id, body: DraftInput):
    story = session.scalar(select(Story).where(Story.id == story_id).with_for_update())
    if not story:
        raise HTTPException(404, "Draft not found")
    if story.status not in {"DRAFT", "CHANGES_REQUESTED"}:
        raise HTTPException(409, "Only draft revisions can be edited here")
    previous = session.scalar(
        select(StoryVersion)
        .where(StoryVersion.story_id == story.id)
        .order_by(StoryVersion.version_number.desc())
        .limit(1)
    )
    if previous.version_number != body.base_version:
        raise HTTPException(409, "This draft changed in another tab. Reload before saving")
    for credit in body.credits:
        if credit.source_id and not session.get(Source, credit.source_id):
            raise HTTPException(422, "A referenced source no longer exists")
    actor = ensure_editor(session)
    ai_metadata = {}
    if body.ai_job_id:
        from app.ai.models import AIJob

        job = session.get(AIJob, body.ai_job_id)
        if not job or job.story_id != story.id or job.status != "SUCCEEDED":
            raise HTTPException(422, "AI preview does not belong to this story or is not ready")
        if job.base_version != previous.version_number:
            raise HTTPException(409, "AI preview is based on an older revision. Generate again")
        ai_metadata = {
            "ai_job_id": str(job.id),
            "human_review_required": True,
            "claims_to_verify": job.result["claims_to_verify"],
            "editorial_warnings": job.result["editorial_warnings"],
        }
    elif previous.content_json.get("human_review_required"):
        ai_metadata = {
            key: previous.content_json[key]
            for key in (
                "ai_job_id",
                "human_review_required",
                "claims_to_verify",
                "editorial_warnings",
            )
            if key in previous.content_json
        }
    version = StoryVersion(
        story_id=story.id,
        version_number=previous.version_number + 1,
        editor_id=actor,
        title=body.title,
        content_json={
            "summary": body.summary,
            "body": body.body,
            "category": body.category,
            "language": body.language or story.language,
            "tags": body.tags,
            "social_captions": body.social_captions,
            **ai_metadata,
        },
    )
    session.add(version)
    session.flush()
    for credit in body.credits:
        session.add(
            StorySource(
                story_id=story.id,
                version_id=version.id,
                ingested_item_id=story.origin_item_id,
                **credit.model_dump(),
                entry_method="manual",
                last_edited_by=actor,
            )
        )
    story.status = "DRAFT"
    story.updated_at = now()
    if body.language:
        story.language = body.language
    warnings = credit_warning([c.model_dump() for c in body.credits])
    audit(
        session,
        "candidate.draft_edited" if story.origin_item_id else "story.draft_edited",
        story.id,
        actor,
        version=version.version_number,
        attribution_warnings=warnings,
    )
    session.commit()
    return draft_view(session, story.id)
