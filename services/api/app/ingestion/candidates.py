import base64
import hashlib
import json
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import Numeric, and_, case, cast, extract, func, or_, select

from app.auth.models import User
from app.editorial.models import Story, StoryVersion
from app.ingestion.models import Feed, FeedEntry, IngestedItem, IngestionSettings, Source
from app.ingestion.policy import collection_settings
from app.ingestion.service import aware, now


def cursor_offset(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        value = int(base64.urlsafe_b64decode(cursor.encode()).decode())
        if 0 <= value <= 1000000:
            return value
    except (ValueError, UnicodeError):
        pass
    raise HTTPException(422, "Invalid cursor")


def next_cursor(offset: int, limit: int, total: int) -> str | None:
    return (
        base64.urlsafe_b64encode(str(offset + limit).encode()).decode()
        if offset + limit < total
        else None
    )


def decode_candidate_cursor(cursor, signature):
    if not cursor:
        return now(), None
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if data["f"] != signature or type(data["p"]) is not bool:
            raise ValueError
        timestamp = aware(datetime.fromisoformat(data["at"]))
        position = (
            data["p"],
            Decimal(data["s"]),
            aware(datetime.fromisoformat(data["c"])),
            uuid.UUID(data["id"]),
        )
        if not position[1].is_finite() or not 0 <= position[1] <= 100:
            raise ValueError
        return timestamp, position
    except (ValueError, UnicodeError, TypeError, KeyError, InvalidOperation):
        raise HTTPException(422, "Invalid candidate cursor or filters changed") from None


def encode_candidate_cursor(row, timestamp, signature):
    item, score = row[:2]
    data = {
        "p": item.pinned,
        "s": str(score),
        "c": aware(item.created_at).isoformat(),
        "id": str(item.id),
        "at": timestamp.isoformat(),
        "f": signature,
    }
    return base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).decode()


def score_expression(session, timestamp: datetime):
    if session.bind.dialect.name == "sqlite":
        age = (func.julianday(timestamp) - func.julianday(IngestedItem.published_at)) * 24
    else:
        age = extract("epoch", timestamp - IngestedItem.published_at) / 3600
    freshness = case(
        (IngestedItem.published_at.is_(None), 25),
        (age < 0, 100),
        (age >= 72, 0),
        else_=100 - age * (100 / 72),
    )
    score = (
        0.30 * IngestedItem.bangladesh_relevance
        + 0.25 * IngestedItem.public_impact
        + 0.20 * freshness
        + 0.15 * IngestedItem.corroboration
        + 0.10 * IngestedItem.uniqueness
    )
    return cast(
        func.round(cast(func.coalesce(IngestedItem.rank_override, score), Numeric(16, 8)), 4),
        Numeric(10, 4),
    )


def attribution_rows(session, item_id):
    rows = session.execute(
        select(FeedEntry, Feed.source_id)
        .join(Feed)
        .where(FeedEntry.item_id == item_id)
        .order_by(FeedEntry.created_at, FeedEntry.id)
    ).all()
    return [
        {
            "source_id": str(source_id),
            "publisher_name": entry.publisher_name,
            "original_url": entry.original_url,
            "rights_status": entry.rights_status,
            "source_type": entry.source_type,
            "published_at": entry.published_at,
            "retrieved_at": entry.created_at,
        }
        for entry, source_id in rows
    ]


def list_candidates(
    session,
    *,
    status="DISCOVERED",
    source_id=None,
    query="",
    category="",
    cursor=None,
    include_inactive=False,
    preferred_only=False,
):
    signature = hashlib.sha256(
        json.dumps(
            [
                status,
                str(source_id),
                query,
                category,
                include_inactive,
                preferred_only,
                collection_settings(session).preferred_categories if preferred_only else [],
            ]
        ).encode()
    ).hexdigest()[:16]
    timestamp, position = decode_candidate_cursor(cursor, signature)
    settings = session.get(IngestionSettings, 1)
    limit = settings.candidate_limit if settings else 30
    latest = (
        select(func.max(StoryVersion.version_number))
        .where(StoryVersion.story_id == Story.id)
        .correlate(Story)
        .scalar_subquery()
    )
    base = (
        select(IngestedItem)
        .outerjoin(Story, Story.origin_item_id == IngestedItem.id)
        .outerjoin(
            StoryVersion,
            and_(StoryVersion.story_id == Story.id, StoryVersion.version_number == latest),
        )
        .outerjoin(User, User.id == Story.author_id)
    )
    display_category = func.coalesce(
        StoryVersion.content_json["category"].as_string(), IngestedItem.category
    )
    criteria = [IngestedItem.id.in_(select(FeedEntry.item_id).join(Feed).join(Source))]
    if not include_inactive:
        criteria.append(
            IngestedItem.id.in_(
                select(FeedEntry.item_id)
                .join(Feed)
                .join(Source)
                .where(
                    Source.active.is_(True),
                    Source.archived_at.is_(None),
                    Source.rights != "prohibited",
                )
            )
        )
    if preferred_only and collection_settings(session).preferred_categories:
        criteria.append(
            func.lower(display_category).in_(
                [c.casefold() for c in collection_settings(session).preferred_categories]
            )
        )
    if status != "all":
        criteria.append(IngestedItem.editorial_status == status)
    if source_id:
        criteria.append(
            IngestedItem.id.in_(
                select(FeedEntry.item_id).join(Feed).where(Feed.source_id == source_id)
            )
        )
    if query:
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        criteria.append(
            or_(
                IngestedItem.title.ilike(pattern, escape="\\"),
                StoryVersion.title.ilike(pattern, escape="\\"),
            )
        )
    if category:
        criteria.append(or_(IngestedItem.category == category, display_category == category))
    score = score_expression(session, timestamp).label("score")
    total = session.scalar(select(func.count()).select_from(base.where(*criteria).subquery())) or 0
    if position:
        pinned, last_score, created, item_id = position
        same_pin = IngestedItem.pinned == pinned
        same_score = score == last_score
        created_column = IngestedItem.created_at
        created_position = created
        if session.bind.dialect.name == "sqlite":
            created_column, created_position = (
                func.julianday(created_column),
                func.julianday(created),
            )
        criteria.append(
            or_(
                and_(IngestedItem.pinned.is_(False), pinned),
                and_(same_pin, score < last_score),
                and_(same_pin, same_score, created_column < created_position),
                and_(
                    same_pin,
                    same_score,
                    created_column == created_position,
                    IngestedItem.id > item_id,
                ),
            )
        )
    rows = session.execute(
        base.with_only_columns(IngestedItem, score, Story, StoryVersion, User)
        .where(*criteria)
        .order_by(
            IngestedItem.pinned.desc(),
            score.desc(),
            IngestedItem.created_at.desc(),
            IngestedItem.id,
        )
        .limit(limit + 1)
    ).all()
    following = (
        encode_candidate_cursor(rows[limit - 1], timestamp, signature)
        if len(rows) > limit
        else None
    )
    rows = rows[:limit]
    result = []
    for item, rank, story, version, author in rows:
        credits = attribution_rows(session, item.id)
        story_id = story.id if story else None
        result.append(
            {
                "id": str(item.id),
                "title": item.title,
                "excerpt": item.excerpt,
                "category": item.category,
                "author": item.author,
                "language": item.language,
                "published_at": item.published_at,
                "original_url": item.normalized_url,
                "publisher": credits[0]["publisher_name"] if credits else "",
                "attributions": credits,
                "editorial_status": item.editorial_status,
                "pinned": item.pinned,
                "score": float(rank),
                "rank_override": item.rank_override,
                "bangladesh_relevance": item.bangladesh_relevance,
                "public_impact": item.public_impact,
                "corroboration": item.corroboration,
                "uniqueness": item.uniqueness,
                "story_id": str(story_id) if story_id else None,
                "draft_title": version.title if version else None,
                "draft_category": version.content_json.get("category", "") if version else None,
                "tags": version.content_json.get("tags", []) if version else [],
                "ai_assisted": bool(version and version.content_json.get("human_review_required")),
                "assigned_author": {"id": str(author.id), "name": author.name} if author else None,
                "sources": [
                    {
                        "id": str(source.id),
                        "publisher": source.publisher,
                        "archived": bool(source.archived_at),
                        "active": source.active,
                    }
                    for source in session.scalars(
                        select(Source).where(
                            Source.id.in_([uuid.UUID(c["source_id"]) for c in credits])
                        )
                    )
                ],
            }
        )
    return {
        "items": result,
        "total": total,
        "candidate_limit": limit,
        "next_cursor": following,
    }
