import random
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.editorial.models import AuditEvent
from app.ingestion.models import CollectionRun, Feed, FeedEntry, IngestedItem, Source
from app.ingestion.network import SafeFetcher, SourceError
from app.ingestion.parsing import ParsedFeed, discover_links, parse_feed


def now() -> datetime:
    return datetime.now(UTC)


def aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


def collectible(source) -> bool:
    return (
        source.source_type != "manual"
        and source.extraction_mode == "metadata"
        and source.rights != "prohibited"
    )


def audit(session: Session, action: str, resource_id: uuid.UUID, actor_id=None, **details):
    session.add(
        AuditEvent(actor_id=actor_id, action=action, resource_id=resource_id, event_details=details)
    )


def probe(source, fetcher=None) -> dict:
    if not collectible(source):
        return {
            "supported": False,
            "health": "REFERENCE_ONLY",
            "feeds": [],
            "message": (
                "Saved as a reference. Automated collection is disabled "
                "by source type or usage permissions."
            ),
        }
    fetcher = fetcher or SafeFetcher()
    try:
        document = fetcher.fetch(source.feed_url or source.url)
        try:
            parsed = parse_feed(document)
            feeds = [{"url": document.url, "title": parsed.title}]
        except SourceError:
            if source.source_type != "website" or source.feed_url:
                raise
            links = discover_links(document)
            if not links:
                raise SourceError(
                    "No advertised RSS/Atom/JSON Feed found. "
                    "Add a direct feed URL or keep this as a manual reference"
                ) from None
            failures = []
            for url in links[:3]:
                try:
                    feed_document = fetcher.fetch(url)
                    parsed = parse_feed(feed_document)
                    feeds = [{"url": feed_document.url, "title": parsed.title}]
                    feeds += [
                        {"url": link, "title": "Advertised feed (not tested)"}
                        for link in links
                        if link != feed_document.url
                    ]
                    break
                except SourceError as exc:
                    failures.append(str(exc))
            else:
                raise SourceError("Advertised feeds could not be collected: " + failures[0])
        return {
            "supported": True,
            "health": "READY",
            "feeds": feeds,
            "message": (
                f"Valid feed: {len(parsed.articles)} metadata items; {parsed.skipped} skipped."
            ),
            "sample": [{"title": a.title, "url": a.url} for a in parsed.articles[:3]],
        }
    except SourceError as exc:
        return {"supported": False, "health": "UNSUPPORTED", "feeds": [], "message": str(exc)}


def ingest(session: Session, source: Source, feed: Feed, parsed: ParsedFeed) -> tuple[int, int]:
    inserted = duplicates = 0
    for article in parsed.articles:
        if session.scalar(
            select(FeedEntry.id).where(FeedEntry.feed_id == feed.id, FeedEntry.guid == article.guid)
        ):
            duplicates += 1
            continue
        item = session.scalar(
            select(IngestedItem)
            .where(
                or_(
                    IngestedItem.normalized_url == article.normalized_url,
                    IngestedItem.content_hash == article.content_hash,
                )
            )
            .order_by(IngestedItem.created_at, IngestedItem.id)
            .limit(1)
        )
        created = False
        if not item:
            try:
                with session.begin_nested():
                    item = IngestedItem(
                        normalized_url=article.normalized_url,
                        content_hash=article.content_hash,
                        title=article.title,
                        excerpt=article.excerpt,
                        category=article.category or source.category,
                        language=source.language,
                        author=article.author,
                        published_at=article.published_at,
                    )
                    session.add(item)
                    session.flush()
                created = True
            except IntegrityError:
                # Another source may ingest this canonical article concurrently.
                item = session.scalar(
                    select(IngestedItem)
                    .where(
                        or_(
                            IngestedItem.normalized_url == article.normalized_url,
                            IngestedItem.content_hash == article.content_hash,
                        )
                    )
                    .order_by(IngestedItem.created_at, IngestedItem.id)
                    .limit(1)
                )
                if not item:
                    raise
        try:
            with session.begin_nested():
                session.add(
                    FeedEntry(
                        feed_id=feed.id,
                        item_id=item.id,
                        guid=article.guid,
                        original_url=article.url,
                        publisher_name=article.publisher_name or source.publisher,
                        rights_status=source.rights,
                        source_type=source.source_type,
                        published_at=article.published_at,
                    )
                )
                session.flush()
        except IntegrityError:
            duplicates += 1
            continue
        if created:
            inserted += 1
        else:
            duplicates += 1
    return inserted, duplicates


def next_collection(source: Source, *, failed=False, retry_after=None) -> datetime:
    minutes = (
        min(1440, source.polling_interval * (2 ** min(source.failure_count, 6)))
        if failed
        else source.polling_interval
    )
    seconds = max(300, minutes * 60 + random.uniform(0, minutes * 6))
    if retry_after:
        seconds = max(seconds, min(retry_after, 86400))
    return now() + timedelta(seconds=seconds)


def collect_run(run_id: uuid.UUID, session_factory, fetcher_factory=None) -> dict:
    """Lease the source in PostgreSQL; commit no network work under a row lock."""
    with session_factory() as session:
        run = session.get(CollectionRun, run_id)
        if not run or run.status not in {"PENDING", "RUNNING"}:
            return {"status": "ignored"}
        source = session.scalar(select(Source).where(Source.id == run.source_id).with_for_update())
        if not source.active or not collectible(source):
            run.status, run.message, run.finished_at = (
                "SKIPPED",
                "Source is inactive or reference-only",
                now(),
            )
            session.commit()
            return {"status": "SKIPPED"}
        if source.locked_until and aware(source.locked_until) > now():
            if source.collection_lock_id != run.id:
                run.status, run.message, run.finished_at = (
                    "SKIPPED",
                    "A collection is already running",
                    now(),
                )
                session.commit()
            return {"status": "already_running"}
        source.collection_lock_id, source.locked_until = run.id, now() + timedelta(minutes=5)
        source.last_checked = now()
        run.status, run.message = "RUNNING", "Fetching permitted feed metadata"
        session.commit()

    try:
        with session_factory() as session:
            run = session.get(CollectionRun, run_id)
            source = session.get(Source, run.source_id)
            fields = (
                "url",
                "feed_url",
                "rights",
                "extraction_mode",
                "source_type",
                "publisher",
                "language",
                "category",
            )
            snapshot = {field: getattr(source, field) for field in fields}
            target = source.feed_url or (source.url if source.source_type != "website" else None)
            feed = (
                session.scalar(select(Feed).where(Feed.source_id == source.id, Feed.url == target))
                if target
                else None
            )
            headers = {}
            if feed and feed.etag:
                headers["If-None-Match"] = feed.etag
            if feed and feed.last_modified:
                headers["If-Modified-Since"] = feed.last_modified
            source_id = source.id
            had_success = bool(feed and feed.last_success)
        fetcher = (fetcher_factory or SafeFetcher)()
        if not target:
            result = probe(SimpleNamespace(**snapshot), fetcher)
            if not result["supported"]:
                raise SourceError(result["message"])
            target = result["feeds"][0]["url"]
        document = fetcher.fetch(target, headers)
        if document.status == 304 and not had_success:
            raise SourceError("The source returned HTTP 304 before a successful collection")
        parsed = parse_feed(document) if document.status != 304 else None
        with session_factory() as session:
            # Revalidate under a short lock after network I/O, before any metadata writes.
            run = session.get(CollectionRun, run_id)
            source = session.scalar(
                select(Source).where(Source.id == run.source_id).with_for_update()
            )
            if not source.active or not collectible(source) or source.collection_lock_id != run.id:
                raise SourceError("Source was disabled or changed while collection was running")
            if any(getattr(source, field) != value for field, value in snapshot.items()):
                raise SourceError("Source was edited while collection was running; collect again")
            feed = session.scalar(
                select(Feed).where(Feed.source_id == source_id, Feed.url == target)
            )
            if not feed:
                feed = Feed(source_id=source_id, url=target)
                session.add(feed)
                session.flush()
            if not source.feed_url and source.source_type == "website":
                source.feed_url = target
            if parsed:
                run.inserted, run.duplicates = ingest(session, source, feed, parsed)
                run.skipped = parsed.skipped
                feed.title = parsed.title
                feed.etag = document.headers.get("etag", "")[:500] or None
                feed.last_modified = document.headers.get("last-modified", "")[:200] or None
            feed.last_success = source.last_success = now()
            source.failure_count, source.health, source.last_error = 0, "HEALTHY", None
            source.next_collection_at = next_collection(source)
            source.collection_lock_id = source.locked_until = None
            run.status, run.finished_at = "SUCCEEDED", now()
            run.message = (
                "Not modified (HTTP 304)"
                if not parsed
                else (
                    f"{run.inserted} new candidates; {run.duplicates} duplicates; "
                    f"{run.skipped} skipped"
                )
            )
            audit(
                session,
                "source.collected",
                source.id,
                run_id=str(run.id),
                inserted=run.inserted,
                duplicates=run.duplicates,
                skipped=run.skipped,
            )
            session.commit()
            return {"status": "SUCCEEDED", "inserted": run.inserted, "duplicates": run.duplicates}
    except Exception as exc:
        message = (
            str(exc)
            if isinstance(exc, SourceError)
            else "Collection failed; retry later or test this source"
        )
        with session_factory() as session:
            run = session.get(CollectionRun, run_id)
            source = session.scalar(
                select(Source).where(Source.id == run.source_id).with_for_update()
            )
            run.status, run.message, run.finished_at = "FAILED", message, now()
            if source.collection_lock_id == run.id:
                source.collection_lock_id = source.locked_until = None
                source.failure_count += 1
                source.last_error, source.health = message, "ERROR"
                source.next_collection_at = next_collection(
                    source, failed=True, retry_after=getattr(exc, "retry_after", None)
                )
            audit(
                session, "source.collection_failed", source.id, run_id=str(run.id), reason=message
            )
            session.commit()
        return {"status": "FAILED", "message": message}
