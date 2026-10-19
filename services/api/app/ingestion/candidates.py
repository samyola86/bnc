import base64
import hashlib
import json
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import Numeric, and_, case, cast, extract, func, or_, select

from app.editorial.models import Story
from app.ingestion.models import Feed, FeedEntry, IngestedItem, IngestionSettings, Source
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
    item, score = row
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
    session, *, status="DISCOVERED", source_id=None, query="", category="", cursor=None
):
    signature = hashlib.sha256(
        json.dumps([status, str(source_id), query, category]).encode()
    ).hexdigest()[:16]
    timestamp, position = decode_candidate_cursor(cursor, signature)
    settings = session.get(IngestionSettings, 1)
    limit = settings.candidate_limit if settings else 30
    criteria = [
        IngestedItem.id.in_(
            select(FeedEntry.item_id)
            .join(Feed)
            .join(Source)
            .where(
                Source.active.is_(True),
                Source.rights != "prohibited",
            )
        )
    ]
    if status != "all":
        criteria.append(IngestedItem.editorial_status == status)
    if source_id:
        criteria.append(
            IngestedItem.id.in_(
                select(FeedEntry.item_id).join(Feed).where(Feed.source_id == source_id)
            )
        )
    if query:
        criteria.append(
            IngestedItem.title.ilike(
                "%" + query.replace("%", "\\%").replace("_", "\\_") + "%", escape="\\"
            )
        )
    if category:
        criteria.append(IngestedItem.category == category)
    score = score_expression(session, timestamp).label("score")
    total = session.scalar(select(func.count()).select_from(IngestedItem).where(*criteria)) or 0
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
        select(IngestedItem, score)
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
    for item, rank in rows:
        credits = attribution_rows(session, item.id)
        story_id = session.scalar(select(Story.id).where(Story.origin_item_id == item.id))
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
            }
        )
    return {
        "items": result,
        "total": total,
        "candidate_limit": limit,
        "next_cursor": following,
    }
