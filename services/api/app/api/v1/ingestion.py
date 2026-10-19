import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.editor import ensure_editor, require_editor
from app.db.session import get_session
from app.editorial.drafts import create_draft, draft_view, update_draft
from app.ingestion.candidates import cursor_offset, list_candidates, next_cursor
from app.ingestion.models import CollectionRun, IngestedItem, IngestionSettings, Source
from app.ingestion.schemas import (
    CandidatePatch,
    DraftInput,
    QueueSettingsInput,
    SourceInput,
    TestInput,
)
from app.ingestion.service import audit, collectible, now, probe
from app.ingestion.tasks import enqueue

router = APIRouter(dependencies=[Depends(require_editor)], tags=["source newsroom"])
DB = Annotated[Session, Depends(get_session)]


def source_view(session, source):
    latest = session.scalar(
        select(CollectionRun)
        .where(CollectionRun.source_id == source.id)
        .order_by(CollectionRun.created_at.desc())
        .limit(1)
    )
    fields = [
        *SourceInput.model_fields,
        "id",
        "health",
        "last_checked",
        "last_success",
        "last_error",
        "next_collection_at",
    ]
    result = {name: getattr(source, name) for name in fields}
    result["can_collect"] = source.active and collectible(source)
    result["latest_run"] = run_view(latest) if latest else None
    return result


def run_view(run):
    return {
        name: getattr(run, name)
        for name in [
            "id",
            "source_id",
            "status",
            "message",
            "inserted",
            "duplicates",
            "skipped",
            "created_at",
            "finished_at",
        ]
    }


def get_source(session, source_id, *, lock=False):
    statement = select(Source).where(Source.id == source_id)
    source = session.scalar(statement.with_for_update() if lock else statement)
    if not source:
        raise HTTPException(404, "Source not found")
    return source


@router.get("/sources")
def sources(session: DB, cursor: str | None = Query(None, max_length=100)):
    offset, limit = cursor_offset(cursor), 100
    total = session.scalar(select(func.count()).select_from(Source)) or 0
    rows = session.scalars(
        select(Source).order_by(Source.publisher, Source.id).offset(offset).limit(limit)
    ).all()
    return {
        "items": [source_view(session, s) for s in rows],
        "total": total,
        "next_cursor": next_cursor(offset, limit, total),
    }


@router.post("/sources/test")
def test_source(body: TestInput):
    return probe(body)


@router.post("/sources", status_code=201)
def add_source(body: SourceInput, session: DB):
    actor = ensure_editor(session)
    source = Source(**body.model_dump(), homepage=body.url, next_collection_at=now())
    session.add(source)
    session.flush()
    audit(session, "source.created", source.id, actor)
    session.commit()
    return source_view(session, source)


@router.patch("/sources/{source_id}")
def edit_source(source_id: uuid.UUID, body: dict, session: DB):
    source = get_source(session, source_id, lock=True)
    before = {name: getattr(source, name) for name in SourceInput.model_fields}
    try:
        data = SourceInput.model_validate({**before, **body})
    except ValidationError:
        raise HTTPException(
            422, "Invalid source fields, URL, usage mode, or collection frequency"
        ) from None
    actor = ensure_editor(session)
    changed = [key for key, value in data.model_dump().items() if value != before[key]]
    for key, value in data.model_dump().items():
        setattr(source, key, value)
    source.homepage = data.url
    if changed:
        source.next_collection_at = now() if source.active and collectible(source) else None
        source.health, source.last_error, source.failure_count = "UNTESTED", None, 0
    audit(session, "source.edited", source.id, actor, fields=changed)
    session.commit()
    return source_view(session, source)


@router.post("/sources/{source_id}/test")
def test_saved_source(source_id: uuid.UUID, session: DB):
    source = get_source(session, source_id)
    result = probe(source)
    source.last_checked, source.health, source.last_error = (
        now(),
        result["health"],
        None if result["supported"] else result["message"],
    )
    audit(session, "source.tested", source.id, ensure_editor(session), health=result["health"])
    session.commit()
    return result


def queue_source(session, source):
    if not source.active or not collectible(source):
        raise HTTPException(409, "This source is inactive or reference-only")
    existing = session.scalar(
        select(CollectionRun)
        .where(
            CollectionRun.source_id == source.id, CollectionRun.status.in_(["PENDING", "RUNNING"])
        )
        .limit(1)
    )
    if existing:
        return {"job_id": str(existing.id), "status": existing.status}
    actor = ensure_editor(session)
    run = CollectionRun(source_id=source.id)
    session.add(run)
    session.flush()
    audit(session, "source.collection_requested", source.id, actor, run_id=str(run.id))
    session.commit()
    if not enqueue(run.id):
        raise HTTPException(503, "Collection queue unavailable; retry later")
    return {"job_id": str(run.id), "status": "PENDING"}


@router.post("/sources/{source_id}/collect", status_code=202)
def collect_source(source_id: uuid.UUID, session: DB):
    return queue_source(session, get_source(session, source_id, lock=True))


@router.post("/feeds/{feed_id}/refresh", status_code=202)
def refresh_feed(feed_id: uuid.UUID, session: DB):
    from app.ingestion.models import Feed

    feed = session.get(Feed, feed_id)
    if not feed:
        raise HTTPException(404, "Feed not found")
    return queue_source(session, get_source(session, feed.source_id, lock=True))


@router.get("/ingestion/jobs/{job_id}")
def job(job_id: uuid.UUID, session: DB):
    run = session.get(CollectionRun, job_id)
    if not run:
        raise HTTPException(404, "Collection job not found")
    return run_view(run)


@router.get("/ingestion/settings")
def settings(session: DB):
    row = session.get(IngestionSettings, 1)
    return {"candidate_limit": row.candidate_limit if row else 30}


@router.patch("/ingestion/settings")
def edit_settings(body: QueueSettingsInput, session: DB):
    row = session.get(IngestionSettings, 1)
    if not row:
        row = IngestionSettings(id=1)
        session.add(row)
    row.candidate_limit = body.candidate_limit
    audit(
        session,
        "candidate_queue.configured",
        uuid.UUID(int=1),
        ensure_editor(session),
        candidate_limit=body.candidate_limit,
    )
    session.commit()
    return {"candidate_limit": row.candidate_limit}


@router.get("/feeds/items")
def candidates(
    session: DB,
    status: str = Query("DISCOVERED", pattern="^(DISCOVERED|SELECTED|DRAFT|DISMISSED|all)$"),
    source_id: uuid.UUID | None = None,
    query: str = Query("", max_length=200),
    category: str = Query("", max_length=100),
    cursor: str | None = Query(None, max_length=1024),
):
    return list_candidates(
        session, status=status, source_id=source_id, query=query, category=category, cursor=cursor
    )


@router.patch("/feeds/items/{item_id}")
def edit_candidate(item_id: uuid.UUID, body: CandidatePatch, session: DB):
    item = session.scalar(select(IngestedItem).where(IngestedItem.id == item_id).with_for_update())
    if not item:
        raise HTTPException(404, "Candidate not found")
    changes = body.model_dump(exclude_unset=True)
    if any(value is None for key, value in changes.items() if key != "rank_override"):
        raise HTTPException(422, "Candidate fields cannot be null")
    if body.editorial_status and item.editorial_status == "DRAFT":
        raise HTTPException(409, "This candidate already has a draft")
    for key, value in changes.items():
        setattr(item, key, value)
    audit(session, "candidate.edited", item.id, ensure_editor(session), fields=list(changes))
    session.commit()
    return {"id": str(item.id), "editorial_status": item.editorial_status}


@router.post("/feeds/items/{item_id}/draft", status_code=201)
def candidate_draft(item_id: uuid.UUID, session: DB):
    return create_draft(session, item_id)


@router.get("/stories/{story_id}")
def get_draft(story_id: uuid.UUID, session: DB):
    return draft_view(session, story_id)


@router.patch("/stories/{story_id}")
def save_draft(story_id: uuid.UUID, body: DraftInput, session: DB):
    return update_draft(session, story_id, body)
