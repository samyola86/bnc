import math
import re
import unicodedata
from collections import Counter
from datetime import timedelta

from sqlalchemy import select

from app.ingestion.models import Feed, FeedEntry, IngestedItem, Source
from app.ingestion.service import aware, now
from app.intelligence.classification import controls
from app.intelligence.models import (
    ClusterMember,
    ItemAnalysis,
    ProviderObservation,
    StoryCluster,
    TrendSnapshot,
)

WINDOWS = {"1h": 1, "6h": 6, "24h": 24, "7d": 168}
STOP = {
    "the",
    "a",
    "an",
    "and",
    "of",
    "to",
    "in",
    "on",
    "for",
    "with",
    "says",
    "news",
    "is",
    "at",
    "as",
    "by",
    "from",
    "এবং",
    "ও",
    "এর",
    "নিয়ে",
    "থেকে",
}


def tokens(title):
    return {
        word
        for word in re.findall(
            r"[\w\u0980-\u09ff]+", unicodedata.normalize("NFKC", title).casefold()
        )
        if len(word) > 2 and word not in STOP
    }


def similarity(left, right):
    a, b = tokens(left), tokens(right)
    numbers_a, numbers_b = set(re.findall(r"\d+", left)), set(re.findall(r"\d+", right))
    if numbers_a and numbers_b and not numbers_a.intersection(numbers_b):
        return 0
    if len(a & b) < 3:
        return 1 if left.casefold() == right.casefold() else 0
    return len(a & b) / max(1, len(a | b))


def effective(analysis):
    return {**analysis.result, **analysis.editorial_override} if analysis else {}


def attach(session, item):
    member = session.scalar(select(ClusterMember).where(ClusterMember.item_id == item.id))
    if member:
        return session.get(StoryCluster, member.cluster_id)
    at = aware(item.published_at or item.created_at)
    analysis = session.scalar(select(ItemAnalysis).where(ItemAnalysis.item_id == item.id))
    data = effective(analysis)
    best, best_score = None, 0.55
    for cluster in session.scalars(
        select(StoryCluster).where(
            StoryCluster.last_activity >= at - timedelta(hours=48),
            StoryCluster.last_activity <= at + timedelta(hours=48),
        )
    ):
        score = similarity(item.title, cluster.title)
        if score > 0.35 and (data.get("entities") or data.get("geography")):
            previous = session.scalar(
                select(ItemAnalysis)
                .join(ClusterMember, ClusterMember.item_id == ItemAnalysis.item_id)
                .where(ClusterMember.cluster_id == cluster.id)
                .limit(1)
            )
            other = effective(previous)
            here_geo, there_geo = set(data.get("geography", [])), set(other.get("geography", []))
            if here_geo and there_geo and not here_geo.intersection(there_geo):
                score = 0
            entities = {v.casefold() for v in data.get("entities", [])}
            if entities.intersection(v.casefold() for v in other.get("entities", [])):
                score = min(1, score + 0.05)
        if score > best_score:
            best, best_score = cluster, score
    if not best:
        best = StoryCluster(
            title=item.title,
            category=data.get("primary_category", item.category or "World"),
            keywords=sorted(tokens(item.title))[:15],
            last_activity=at,
            confidence=0.4,
            editorial_lock=False,
        )
        session.add(best)
        session.flush()
    else:
        best.last_activity = max(aware(best.last_activity), at)
        best.confidence = min(0.95, best_score)
    session.add(ClusterMember(cluster_id=best.id, item_id=item.id))
    session.flush()
    return best


def evidence(session, item_ids):
    rows = session.execute(
        select(FeedEntry, Source)
        .join(Feed, Feed.id == FeedEntry.feed_id)
        .join(Source, Source.id == Feed.source_id)
        .where(FeedEntry.item_id.in_(item_ids))
    ).all()
    return [
        {
            "item_id": str(entry.item_id),
            "publisher": entry.publisher_name,
            "url": entry.original_url,
            "rights": entry.rights_status,
            "provider": source.source_type,
            "source_id": str(source.id),
            "metadata": entry.provider_metadata,
            "unresolved_redirect": "news.google.com/" in entry.original_url,
            "eligible": source.active
            and not source.archived_at
            and source.rights != "prohibited"
            and entry.rights_status != "prohibited",
        }
        for entry, source in rows
    ]


def priority_values(item, moment, quality, at, weights, classification=None):
    data = classification or {}
    age = (
        max(0, (at - aware(item.published_at)).total_seconds() / 3600)
        if item.published_at
        else None
    )
    freshness = max(0, 100 - age * 100 / 72) if age is not None else 25
    factors = {
        "bangladesh_relevance": data.get("bangladesh_relevance", item.bangladesh_relevance)
        if item.bangladesh_relevance == 50
        else item.bangladesh_relevance,
        "public_impact": data.get("public_interest", item.public_impact)
        if item.public_impact == 50
        else item.public_impact,
        "trend_momentum": moment,
        "evidence_quality": quality,
        "freshness_originality": (freshness + item.uniqueness) / 2,
    }
    value = sum(factors[k] * weights[k] for k in weights)
    return round(float(item.rank_override if item.rank_override is not None else value), 2), factors


def measure(session, cluster, window, at=None, *, store=True):
    at = at or now()
    hours = WINDOWS[window]
    items = session.scalars(
        select(IngestedItem)
        .join(ClusterMember, ClusterMember.item_id == IngestedItem.id)
        .where(ClusterMember.cluster_id == cluster.id)
    ).all()
    refs = evidence(session, [i.id for i in items])
    eligible_ids = {r["item_id"] for r in refs if r["eligible"]}
    items = [i for i in items if str(i.id) in eligible_ids]
    dates = [aware(i.published_at or i.created_at) for i in items]
    count = sum(at - timedelta(hours=hours) <= d <= at for d in dates)
    baseline = sum(
        at - timedelta(hours=hours * 2) <= d < at - timedelta(hours=hours) for d in dates
    )
    # Bayesian-style smoothing avoids infinite growth from a zero baseline.
    momentum = round(max(0, min(100, 50 + 25 * math.log2((count + 1) / (baseline + 1)))), 2)
    if count == baseline == 0:
        momentum = 0
    item_dates = {str(i.id): aware(i.published_at or i.created_at) for i in items}
    recent_publishers = {
        r["publisher"].casefold()
        for r in refs
        if r["eligible"]
        and r["item_id"] in item_dates
        and at - timedelta(hours=hours) <= item_dates[r["item_id"]] <= at
    }
    previous_publishers = {
        r["publisher"].casefold()
        for r in refs
        if r["eligible"]
        and r["item_id"] in item_dates
        and at - timedelta(hours=hours * 2)
        <= item_dates[r["item_id"]]
        < at - timedelta(hours=hours)
    }
    breadth = max(
        0,
        min(
            100, 50 + 25 * math.log2((len(recent_publishers) + 1) / (len(previous_publishers) + 1))
        ),
    )
    if count or baseline:
        momentum = round(0.8 * momentum + 0.2 * breadth, 2)
    coverage_momentum = momentum
    engagement_changes = []
    for reference in refs:
        if reference["provider"] != "INSTAGRAM_ACCOUNT" or not reference["eligible"]:
            continue
        history = session.scalars(
            select(ProviderObservation)
            .where(
                ProviderObservation.provider == "instagram",
                ProviderObservation.topic == reference["url"],
                ProviderObservation.observed_at >= at - timedelta(hours=hours * 2),
                ProviderObservation.observed_at <= at,
            )
            .order_by(ProviderObservation.observed_at)
        ).all()
        if len(history) >= 2:
            before, after = history[0].metrics, history[-1].metrics
            delta = sum(
                max(0, after.get(k, 0) - before.get(k, 0)) for k in ("like_count", "comments_count")
            )
            engagement_changes.append({"url": reference["url"], "delta": delta})
    if engagement_changes:
        engagement_score = min(100, 20 * math.log1p(sum(v["delta"] for v in engagement_changes)))
        momentum = round(0.85 * momentum + 0.15 * engagement_score, 2)
    direction = "rising" if count > baseline else "falling" if count < baseline else "steady"
    publishers = sorted(
        {r["publisher"].strip().casefold() for r in refs if r["eligible"] and r["publisher"]}
    )
    texts = Counter(i.content_hash for i in items)
    syndicated = sum(v - 1 for v in texts.values() if v > 1) + max(0, len(publishers) - len(items))
    quality = min(
        70,
        25
        + (15 if any(i.excerpt for i in items) else 0)
        + (15 if any(i.published_at for i in items) else 0)
        + (15 if any(not r["unresolved_redirect"] for r in refs) else 0),
    )
    if any(r["provider"] == "INSTAGRAM_ACCOUNT" for r in refs):
        quality = min(quality, 35)
    _, config = controls(session)
    analysed = []
    analysis_records = []
    for item in items:
        analysis = session.scalar(select(ItemAnalysis).where(ItemAnalysis.item_id == item.id))
        if analysis:
            analysis_records.append(
                {
                    "item_id": str(item.id),
                    "model": analysis.model,
                    "prompt_version": analysis.prompt_version,
                    "analysed_at": analysis.updated_at,
                    "classification": effective(analysis),
                    "editorial_override": analysis.editorial_override,
                }
            )
        score, factors = priority_values(
            item, momentum, quality, at, config.weights, effective(analysis)
        )
        analysed.append((score, item, factors, effective(analysis)))
        if store and window == "24h":
            item.trend_momentum, item.evidence_quality = momentum, quality
            item.intelligence_score = score
    winner = max(analysed, key=lambda row: row[0]) if analysed else None
    score = (
        cluster.score_override if cluster.score_override is not None else winner[0] if winner else 0
    )
    warnings = [
        "Machine-generated recommendation; not approved or fact-checked",
        "Publisher counts measure coverage, not independent confirmations or public popularity",
        "Headline/summary evidence only",
    ]
    if syndicated:
        warnings.append("Repeated or syndicated coverage detected")
    if any(r["provider"] == "INSTAGRAM_ACCOUNT" for r in refs):
        warnings.append("Instagram reporting lead requires corroboration")
    signals = {
        "count": count,
        "baseline_count": baseline,
        "publisher_count": len(publishers),
        "publishers": publishers,
        "independent_confirmations": None,
        "syndicated_copies": syndicated,
        "direction": direction,
        "evidence_quality": quality,
        "google_trends": None,
        "instagram_engagement": [r["metadata"] for r in refs if r["metadata"]] or None,
        "instagram_engagement_changes": engagement_changes or None,
        "coverage_momentum": coverage_momentum,
        "recent_publisher_labels": len(recent_publishers),
        "baseline_publisher_labels": len(previous_publishers),
        "explanation": (
            f"{count} reports in {window}, compared with {baseline} "
            "in the preceding equal window. Coverage momentum only."
        ),
        "factors": winner[2] if winner else {},
        "weights": config.weights,
        "contributions": {
            key: round(value * config.weights[key], 2) for key, value in winner[2].items()
        }
        if winner
        else {},
        "warnings": warnings,
    }
    if store:
        bucket = at.replace(minute=(at.minute // 15) * 15, second=0, microsecond=0)
        snap = session.scalar(
            select(TrendSnapshot).where(
                TrendSnapshot.cluster_id == cluster.id,
                TrendSnapshot.window == window,
                TrendSnapshot.bucket == bucket,
            )
        )
        if not snap:
            snap = TrendSnapshot(cluster_id=cluster.id, window=window, bucket=bucket)
            session.add(snap)
        snap.momentum, snap.score, snap.signals = momentum, score, signals
    return {
        "id": str(cluster.id),
        "title": cluster.title,
        "category": winner[3].get("primary_category", cluster.category)
        if winner
        else cluster.category,
        "tags": winner[3].get("tags", []) if winner else [],
        "keywords": cluster.keywords,
        "score": score,
        "momentum": momentum,
        "last_activity": cluster.last_activity,
        "confidence": cluster.confidence,
        "pinned": cluster.pinned,
        "dismissed": cluster.dismissed,
        "window": window,
        "analysis_at": at,
        "first_detected": cluster.created_at,
        "evidence_summary": (
            f"{len(items)} distinct stored items across {len(publishers)} "
            "publisher labels. Independent confirmation has not been established."
        ),
        "signals": signals,
        "analyses": analysis_records,
        "sources": refs,
        "items": [
            {
                "id": str(i.id),
                "title": i.title,
                "published_at": i.published_at,
                "url": i.normalized_url,
            }
            for i in items
        ],
        "representative_item_id": str(winner[1].id) if winner else None,
    }
