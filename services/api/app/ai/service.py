import hashlib
import json
import uuid
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, select

from app.ai.models import AIJob
from app.ai.schemas import GenerateInput
from app.auth.editor import ensure_editor
from app.auth.models import User
from app.config import get_settings
from app.editorial.drafts import draft_view
from app.editorial.models import Story
from app.ingestion.models import IngestedItem, Source
from app.ingestion.service import audit, aware, now


def expire_job(job):
    if job.status in {"PENDING", "RUNNING"} and aware(job.created_at) < now() - timedelta(
        minutes=5
    ):
        job.status, job.message, job.finished_at = (
            "FAILED",
            "AI job expired. Check the worker and generate again",
            now(),
        )


def job_view(job):
    return {
        key: getattr(job, key)
        for key in (
            "id",
            "story_id",
            "base_version",
            "model",
            "template_version",
            "status",
            "message",
            "result",
            "usage",
            "created_at",
            "finished_at",
        )
    }


def evidence_packet(session, story, body):
    draft = draft_view(session, story.id)
    evidence = []
    if story.origin_item_id:
        item = session.get(IngestedItem, story.origin_item_id)
        origins = draft["provenance"]
        # The canonical excerpt has no per-occurrence content snapshot. Be conservative
        # when any provenance/registry record forbids using its material.
        permitted = bool(origins)
        for credit in origins:
            source = session.get(Source, uuid.UUID(credit["source_id"]))
            permitted = permitted and bool(
                source
                and source.rights in {"metadata_only", "licensed", "owned"}
                and source.extraction_mode == "metadata"
                and credit["rights_status"] in {"metadata_only", "licensed", "owned"}
            )
        if permitted and item.excerpt.strip():
            evidence.append(
                {
                    "id": str(item.id),
                    "kind": "feed_metadata",
                    "headline": item.title,
                    "text": item.excerpt[:12000],
                    "attributions": [
                        {
                            key: str(credit[key]) if credit[key] is not None else None
                            for key in (
                                "source_id",
                                "publisher_name",
                                "original_url",
                                "rights_status",
                                "published_at",
                            )
                        }
                        for credit in origins
                    ],
                }
            )
    if body.reporting_notes.strip():
        if not body.notes_permitted:
            raise HTTPException(
                422, "Confirm that your reporting notes are permitted for AI drafting"
            )
        evidence.append(
            {"id": "editor-notes", "kind": "editor_reporting", "text": body.reporting_notes.strip()}
        )
    if not evidence:
        raise HTTPException(
            422,
            "No permitted evidence is available. Add factual reporting notes you may use; "
            "URLs alone are not evidence",
        )
    return {"language": body.language, "evidence": evidence}


def request_job(session, story_id, body: GenerateInput):
    settings = get_settings()
    if not settings.openai_api_key or not settings.openai_model:
        raise HTTPException(
            503,
            "AI is not configured. Set OPENAI_API_KEY and OPENAI_MODEL on API and worker servers",
        )
    story = session.scalar(select(Story).where(Story.id == story_id).with_for_update())
    if not story:
        raise HTTPException(404, "Draft not found")
    actor = ensure_editor(session)
    # Lock story before user, matching revision writes and avoiding a cycle with
    # PostgreSQL's editor foreign-key locks. Serialize cross-story quota reservations.
    session.scalar(select(User).where(User.id == actor).with_for_update())
    if story.status not in {"DRAFT", "CHANGES_REQUESTED"}:
        raise HTTPException(409, "AI drafting is available only for editable drafts")
    if draft_view(session, story.id)["version"] != body.base_version:
        raise HTTPException(409, "The saved story changed. Reload before generating")
    active = session.scalars(
        select(AIJob).where(
            AIJob.story_id == story.id,
            AIJob.status.in_(["PENDING", "RUNNING"]),
        )
    ).all()
    for job in active:
        expire_job(job)
        if job.status in {"PENDING", "RUNNING"}:
            raise HTTPException(409, "This story already has an AI job running")
    count = session.scalar(
        select(func.count())
        .select_from(AIJob)
        .where(
            AIJob.editor_id == actor,
            AIJob.created_at >= now() - timedelta(hours=1),
        )
    )
    if count >= settings.ai_hourly_limit:
        raise HTTPException(429, "Editor AI generation limit reached. Try again in an hour")
    packet = evidence_packet(session, story, body)
    encoded = json.dumps(packet, sort_keys=True, ensure_ascii=False)
    job = AIJob(
        story_id=story.id,
        editor_id=actor,
        base_version=body.base_version,
        model=settings.openai_model,
        input_hash=hashlib.sha256(encoded.encode()).hexdigest(),
        input_json=packet,
    )
    session.add(job)
    session.flush()
    audit(session, "ai.requested", story.id, actor, job_id=str(job.id), version=body.base_version)
    session.commit()
    return job
