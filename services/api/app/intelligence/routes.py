import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.editor import current_user, ensure_editor, require_editor, require_superadmin
from app.config import get_settings
from app.db.session import get_session
from app.editorial.drafts import create_draft
from app.ingestion.models import Feed, IngestedItem, Source
from app.ingestion.network import SafeFetcher, SourceError
from app.ingestion.parsing import ParsedFeed, article, plain_text
from app.ingestion.service import audit, ingest, now
from app.intelligence.analytics import effective, measure
from app.intelligence.classification import controls
from app.intelligence.models import (
    ClusterMember,
    IntelligenceUsage,
    ItemAnalysis,
    StoryCluster,
    TrendSnapshot,
)
from app.intelligence.providers import GDELT, GoogleTrends, instagram_link
from app.intelligence.schemas import Controls

router = APIRouter(
    prefix="/intelligence", dependencies=[Depends(require_editor)], tags=["news intelligence"]
)
DB = Annotated[Session, Depends(get_session)]


def editor_only(session):
    if current_user(session).role not in {"EDITOR", "SUPERADMIN"}:
        raise HTTPException(403, "Only Editors and Superadmins can change intelligence decisions")


def cluster_or_404(session, cluster_id):
    cluster = session.get(StoryCluster, cluster_id)
    if not cluster:
        raise HTTPException(404, "Trend not found")
    return cluster


@router.get("/settings", dependencies=[Depends(require_superadmin)])
def settings(session: DB):
    row, config = controls(session)
    result = {"config": config.model_dump(), "last_cycle": row.last_cycle}
    env = get_settings()
    result["supported_models"] = (
        [env.openai_classification_model] if env.openai_classification_model else []
    )
    result["classification_ready"] = bool(
        env.openai_api_key
        and env.openai_classification_model
        and env.openai_classification_input_per_million > 0
        and env.openai_classification_output_per_million > 0
    )
    result["rates"] = {
        "input_per_million": env.openai_classification_input_per_million,
        "output_per_million": env.openai_classification_output_per_million,
    }
    result["providers"] = [
        GoogleTrends().status(),
        {
            "provider": "instagram",
            "status": "CONFIGURED"
            if env.meta_instagram_token and env.meta_instagram_account_id
            else "MANUAL_LINKS_ONLY",
        },
        {"provider": "gdelt", "status": "PUBLIC_METADATA"},
        {"provider": "google_news", "status": "RSS_DISCOVERY"},
    ]
    day = now().date().isoformat()
    rows = session.scalars(select(IntelligenceUsage).where(IntelligenceUsage.day == day)).all()
    result["usage"] = {
        "day": day,
        "requests": len(rows),
        "input_tokens": sum(r.input_tokens for r in rows),
        "output_tokens": sum(r.output_tokens for r in rows),
        "accounted_usd": float(
            sum(r.cost_usd if r.cost_usd is not None else r.reserved_usd for r in rows)
        ),
        "uncertain_requests": sum(r.cost_usd is None for r in rows),
    }
    result["recent_errors"] = [r.error for r in rows if r.error][-10:]
    session.commit()
    return result


@router.patch("/settings", dependencies=[Depends(require_superadmin)])
def update_settings(body: dict, session: DB):
    row, previous = controls(session, lock=True)
    try:
        updated = Controls.model_validate({**previous.model_dump(), **body})
    except ValueError:
        raise HTTPException(422, "Invalid intelligence settings or taxonomy") from None
    if updated.model and updated.model != get_settings().openai_classification_model:
        raise HTTPException(422, "Select the server-configured classification model")
    row.config = updated.model_dump()
    audit(
        session,
        "intelligence.settings_changed",
        uuid.UUID(int=0),
        ensure_editor(session),
        fields=list(body),
    )
    session.commit()
    return settings(session)


@router.post("/cycle", status_code=202, dependencies=[Depends(require_superadmin)])
def cycle():
    from app.intelligence.tasks import intelligence_cycle

    try:
        job = intelligence_cycle.delay()
        return {"job_id": job.id, "status": "QUEUED"}
    except Exception:
        raise HTTPException(503, "Intelligence queue unavailable; retry later") from None


@router.post("/provision", dependencies=[Depends(require_superadmin)])
def provision_sources(session: DB):
    from app.intelligence.provision import provision

    return {"created": provision(session, test=False)}


@router.get("/trends")
@router.get("/recommendations")
def trends(
    session: DB,
    window: Literal["1h", "6h", "24h", "7d"] = "24h",
    category: str = "",
    geography: Literal["all", "BD", "global"] = "all",
    query: str = Query("", max_length=200),
    order: Literal["priority", "momentum"] = "priority",
    unreviewed: bool = False,
    needs_verification: bool = False,
    offset: int = Query(0, ge=0, le=10000),
    limit: int = Query(30, ge=1, le=50),
):
    clusters = session.scalars(
        select(StoryCluster)
        .where(StoryCluster.dismissed.is_(False))
        .order_by(StoryCluster.last_activity.desc())
        .limit(500)
    ).all()
    result = []
    for cluster in clusters:
        data = measure(session, cluster, window, store=False)
        if (
            not data["items"]
            or (category and data["category"] != category)
            or (
                query
                and query.casefold() not in (data["title"] + " ".join(data["keywords"])).casefold()
            )
        ):
            continue
        bd = data["signals"]["factors"].get("bangladesh_relevance", 0) >= 60
        if (geography == "BD" and not bd) or (geography == "global" and bd):
            continue
        if unreviewed and any(
            session.get(IngestedItem, uuid.UUID(i["id"])).editorial_status != "DISCOVERED"
            for i in data["items"]
        ):
            continue
        if needs_verification and not data["signals"]["warnings"]:
            continue
        result.append(data)
    result.sort(
        key=lambda d: (d["pinned"], d["momentum"] if order == "momentum" else d["score"]),
        reverse=True,
    )
    return {
        "items": result[offset : offset + limit],
        "total": len(result),
        "next_offset": offset + limit if offset + limit < len(result) else None,
        "coverage_limit": 500,
    }


@router.get("/trends/{cluster_id}")
def detail(cluster_id: uuid.UUID, session: DB, window: Literal["1h", "6h", "24h", "7d"] = "24h"):
    data = measure(session, cluster_or_404(session, cluster_id), window, store=False)
    history = session.scalars(
        select(TrendSnapshot)
        .where(TrendSnapshot.cluster_id == cluster_id, TrendSnapshot.window == window)
        .order_by(TrendSnapshot.bucket.desc())
        .limit(100)
    ).all()
    return {
        **data,
        "history": [
            {"at": h.bucket, "momentum": h.momentum, "score": h.score, "signals": h.signals}
            for h in history
        ],
    }


class ClusterEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pinned: bool | None = None
    dismissed: bool | None = None
    score_override: int | None = Field(default=None, ge=0, le=100)


@router.patch("/trends/{cluster_id}")
def edit_cluster(cluster_id: uuid.UUID, body: ClusterEdit, session: DB):
    editor_only(session)
    cluster = cluster_or_404(session, cluster_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is None and key != "score_override":
            raise HTTPException(422, "Only the score override can be cleared")
        setattr(cluster, key, value)
    audit(
        session,
        "intelligence.cluster_override",
        cluster.id,
        ensure_editor(session),
        changes=body.model_dump(exclude_unset=True),
    )
    session.commit()
    return detail(cluster_id, session)


class Move(BaseModel):
    item_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    target_cluster_id: uuid.UUID | None = None


@router.post("/trends/{cluster_id}/move")
def move(cluster_id: uuid.UUID, body: Move, session: DB):
    editor_only(session)
    cluster = cluster_or_404(session, cluster_id)
    members = session.scalars(
        select(ClusterMember)
        .where(ClusterMember.cluster_id == cluster_id, ClusterMember.item_id.in_(body.item_ids))
        .with_for_update()
    ).all()
    if len(members) != len(set(body.item_ids)):
        raise HTTPException(422, "Select items from this cluster")
    target = (
        cluster_or_404(session, body.target_cluster_id)
        if body.target_cluster_id
        else StoryCluster(
            title=session.get(IngestedItem, body.item_ids[0]).title,
            category=cluster.category,
            keywords=cluster.keywords,
            last_activity=now(),
            confidence=1,
            editorial_lock=True,
        )
    )
    session.add(target)
    session.flush()
    for member in members:
        member.cluster_id, member.editorial_lock = target.id, True
    cluster.editorial_lock = target.editorial_lock = True
    audit(
        session,
        "intelligence.cluster_move",
        cluster_id,
        ensure_editor(session),
        target=str(target.id),
        items=[str(i) for i in body.item_ids],
    )
    session.commit()
    return {"id": str(target.id)}


@router.post("/trends/{cluster_id}/select")
def select_cluster(cluster_id: uuid.UUID, session: DB):
    editor_only(session)
    data = measure(session, cluster_or_404(session, cluster_id), "24h", store=False)
    if not data["representative_item_id"]:
        raise HTTPException(422, "No eligible source metadata")
    item = session.get(IngestedItem, uuid.UUID(data["representative_item_id"]))
    if item.editorial_status == "DISCOVERED":
        item.editorial_status = "SELECTED"
    audit(session, "intelligence.selected", cluster_id, ensure_editor(session))
    session.commit()
    return {"item_id": str(item.id)}


@router.post("/trends/{cluster_id}/draft")
def draft(cluster_id: uuid.UUID, session: DB):
    data = measure(session, cluster_or_404(session, cluster_id), "24h", store=False)
    if not data["representative_item_id"]:
        raise HTTPException(422, "No eligible source metadata")
    item_id = uuid.UUID(data["representative_item_id"])
    analysis = session.scalar(select(ItemAnalysis).where(ItemAnalysis.item_id == item_id))
    suggestions = {
        "category": data["category"],
        "tags": data["tags"],
        "model": analysis.model if analysis else "unanalysed",
        "prompt_version": analysis.prompt_version if analysis else "",
    }
    return create_draft(session, item_id, suggestions=suggestions)


class AnalysisEdit(BaseModel):
    primary_category: str
    tags: list[str] = Field(max_length=20)


@router.patch("/items/{item_id}/classification")
def override_classification(item_id: uuid.UUID, body: AnalysisEdit, session: DB):
    editor_only(session)
    _, config = controls(session)
    analysis = session.scalar(select(ItemAnalysis).where(ItemAnalysis.item_id == item_id))
    if not analysis:
        raise HTTPException(409, "Wait for initial analysis")
    if body.primary_category not in config.taxonomy or any(len(t) > 100 for t in body.tags):
        raise HTTPException(422, "Invalid category or tags")
    analysis.editorial_override = body.model_dump()
    audit(
        session,
        "intelligence.classification_override",
        item_id,
        ensure_editor(session),
        changes=body.model_dump(),
    )
    session.commit()
    return effective(analysis)


class ManualPost(BaseModel):
    url: str
    title: str = Field(min_length=1, max_length=500)
    caption: str = Field(default="", max_length=1200)


@router.post("/sources/{source_id}/instagram-post", status_code=201)
def manual_post(source_id: uuid.UUID, body: ManualPost, session: DB):
    editor_only(session)
    source = session.get(Source, source_id)
    if not source or source.source_type != "INSTAGRAM_ACCOUNT":
        raise HTTPException(422, "Choose an Instagram source")
    if source.archived_at or source.rights == "prohibited":
        raise HTTPException(403, "Source permissions prohibit this lead")
    try:
        link = instagram_link(body.url)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    feed = session.scalar(select(Feed).where(Feed.source_id == source.id, Feed.url == source.url))
    if not feed:
        feed = Feed(source_id=source.id, url=source.url, title=source.publisher)
        session.add(feed)
        session.flush()
    if not plain_text(body.title, 500):
        raise HTTPException(422, "Lead headline must not be blank")
    inserted, duplicates = ingest(
        session,
        source,
        feed,
        ParsedFeed(
            source.publisher,
            [article(link, link, body.title, body.caption, publisher_name=source.publisher)],
        ),
    )
    audit(session, "intelligence.instagram_lead_added", source.id, ensure_editor(session), url=link)
    session.commit()
    return {
        "inserted": inserted,
        "duplicates": duplicates,
        "warning": "Unverified reporting lead; manual account attribution must be checked",
    }


@router.get("/gdelt-timeline")
def gdelt_timeline(query: str = Query(min_length=2, max_length=200)):
    try:
        return {
            "timeline": GDELT().timeline(query, SafeFetcher()),
            "meaning": "Publisher coverage, not independent confirmations",
        }
    except (SourceError, ValueError):
        raise HTTPException(503, "GDELT timeline unavailable") from None
