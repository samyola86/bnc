import json
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from html import escape
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from app.api.v1 import ingestion as routes
from app.auth.editor import EDITOR_ID
from app.auth.models import User
from app.config import get_settings
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.session import get_session
from app.editorial.models import AuditEvent, StorySource, StoryVersion
from app.ingestion import service, tasks
from app.ingestion.models import CollectionRun, Feed, FeedEntry, IngestedItem, Source
from app.ingestion.network import Document, SourceError
from app.ingestion.parsing import parse_feed
from app.ingestion.service import collect_run, now, probe
from app.main import app


def rss(count=1, *, url="https://publisher.example/story", title="River report", etag="v1"):
    items = "".join(
        f"""<item><guid>{url}/{index}</guid>
      <link>{escape(url + "/" + str(index) + "?utm_source=feed")}</link>
      <title>{escape(title)} {index}</title><description>Verified feed excerpt {index}</description>
      <category>Bangladesh</category><author>Reporter</author>
      <pubDate>Mon, 19 Oct 2026 01:00:00 GMT</pubDate></item>"""
        for index in range(count)
    )
    return Document(
        "https://publisher.example/feed",
        200,
        f'<rss version="2.0"><channel><title>Publisher feed</title><link>https://publisher.example/</link><description>News</description>{items}</channel></rss>'.encode(),
        {"etag": etag, "last-modified": "Mon, 19 Oct 2026 01:00:00 GMT"},
    )


class FakeWeb:
    def __init__(self):
        self.documents = {"https://publisher.example/feed": rss()}
        self.calls = []
        self.on_fetch = None

    def fetch(self, url, headers=None):
        self.calls.append((url, headers or {}))
        if self.on_fetch:
            self.on_fetch()
        document = self.documents.get(url)
        if isinstance(document, Exception):
            raise document
        if document is None:
            raise SourceError("No advertised feed was found")
        return document


@pytest.fixture
def newsroom(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'newsroom.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def session_override():
        with factory() as session:
            yield session

    web = FakeWeb()
    monkeypatch.setattr(get_settings(), "ingestion_api_token", "test-editor-token")
    monkeypatch.setattr(service, "SafeFetcher", lambda: web)
    monkeypatch.setattr(tasks, "SessionLocal", factory)
    monkeypatch.setattr(routes, "enqueue", lambda run_id: bool(collect_run(run_id, factory)))
    app.dependency_overrides[get_session] = session_override
    with TestClient(app, headers={"Authorization": "Bearer test-editor-token"}) as client:
        yield client, factory, web
    app.dependency_overrides.clear()
    engine.dispose()


def add_source(client, **values):
    response = client.post(
        "/api/v1/sources",
        json={
            "publisher": "Original publisher",
            "url": "https://publisher.example/feed",
            "language": "en",
            **values,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def collect(client, source):
    response = client.post(f"/api/v1/sources/{source['id']}/collect")
    assert response.status_code == 202, response.text
    return client.get(f"/api/v1/ingestion/jobs/{response.json()['job_id']}").json()


def candidates(client, **params):
    response = client.get("/api/v1/feeds/items", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_complete_website_feed_candidate_and_attributed_draft_workflow(newsroom):
    client, factory, web = newsroom
    homepage = "https://publisher.example/"
    web.documents[homepage] = Document(
        homepage,
        200,
        b'<html><head><link rel="alternate" type="application/rss+xml" href="/feed"></head></html>',
        {},
    )
    result = client.post("/api/v1/sources/test", json={"url": homepage, "source_type": "website"})
    assert result.json()["supported"]
    assert result.json()["feeds"][0]["url"] == "https://publisher.example/feed"
    source = add_source(client, url=homepage, source_type="website")
    assert collect(client, source)["inserted"] == 1
    item = candidates(client)["items"][0]
    assert item["publisher"] == "Original publisher"
    assert item["category"] == "Bangladesh"
    assert item["published_at"].startswith("2026-10-19T01:00:00")
    assert item["original_url"] == "https://publisher.example/story/0"
    assert item["editorial_status"] == "DISCOVERED"
    assert collect(client, source)["duplicates"] == 1
    draft = client.post(f"/api/v1/feeds/items/{item['id']}/draft").json()
    assert draft["credits"][0]["publisher_name"] == "Original publisher"
    assert draft["credits"][0]["original_url"].endswith("?utm_source=feed")
    assert draft["body"] == ""  # Do not copy a publisher article into BNC's body.
    assert draft["warnings"] == []
    assert client.post(f"/api/v1/feeds/items/{item['id']}/draft").json()["id"] == draft["id"]
    patch = {
        "base_version": 1,
        "title": "Original BNC headline",
        "body": "Our reporting",
        "summary": "Editor-written summary",
        "category": "Environment",
        "credits": [
            {"publisher_name": "Manual credit without a URL", "attribution_text": "Interview"}
        ],
    }
    edited = client.patch(f"/api/v1/stories/{draft['id']}", json=patch)
    assert edited.status_code == 200, edited.text
    assert edited.json()["version"] == 2
    assert edited.json()["credits"][0]["original_url"] is None
    assert edited.json()["provenance"][0]["publisher_name"] == "Original publisher"
    assert client.patch(f"/api/v1/stories/{draft['id']}", json=patch).status_code == 409
    missing = client.patch(
        f"/api/v1/stories/{draft['id']}", json={**patch, "base_version": 2, "credits": []}
    )
    assert missing.status_code == 200
    assert missing.json()["warnings"] == ["Missing source credit"]
    assert missing.json()["attribution_blocks_publishing"] is False
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(IngestedItem)) == 1
        assert session.scalar(select(func.count()).select_from(FeedEntry)) == 1
        assert session.scalar(select(func.count()).select_from(StoryVersion)) == 3
        assert session.scalar(select(func.count()).select_from(StorySource)) == 2
        assert session.scalar(
            select(AuditEvent)
            .where(AuditEvent.action == "candidate.draft_edited")
            .order_by(AuditEvent.created_at.desc())
            .limit(1)
        )
        assert session.scalar(select(IngestedItem.title)) == "River report 0"
    assert candidates(client, status="DRAFT")["items"][0]["story_id"] == draft["id"]


def test_cross_feed_url_and_content_deduplication_retains_every_source(newsroom):
    client, factory, web = newsroom
    first = add_source(client)
    second = add_source(client, publisher="Syndicated publisher", url="https://second.example/rss")
    third = add_source(client, publisher="Third publisher", url="https://third.example/rss")
    web.documents[second["url"]] = rss()
    web.documents[third["url"]] = rss(url="https://third.example/other-url")
    assert collect(client, first)["inserted"] == 1
    assert collect(client, second)["duplicates"] == 1
    assert collect(client, third)["duplicates"] == 1
    data = candidates(client)
    assert data["total"] == 1
    assert len(data["items"][0]["attributions"]) == 3
    assert data["items"][0]["corroboration"] == 0
    for source in [first, second]:
        assert (
            client.patch(f"/api/v1/sources/{source['id']}", json={"active": False}).status_code
            == 200
        )
    assert candidates(client)["total"] == 1
    client.patch(f"/api/v1/sources/{third['id']}", json={"active": False})
    assert candidates(client)["total"] == 0
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(FeedEntry)) == 3


def test_configurable_queue_pagination_pins_selection_and_filters(newsroom):
    client, _, web = newsroom
    web.documents["https://publisher.example/feed"] = rss(75)
    source = add_source(client)
    assert collect(client, source)["inserted"] == 75
    assert (
        client.patch("/api/v1/ingestion/settings", json={"candidate_limit": 19}).status_code == 422
    )
    client.patch("/api/v1/ingestion/settings", json={"candidate_limit": 20})
    seen, cursor = set(), None
    for expected in [20, 20, 20, 15]:
        page = candidates(client, **({"cursor": cursor} if cursor else {}))
        assert len(page["items"]) == expected
        seen.update(item["id"] for item in page["items"])
        cursor = page["next_cursor"]
    assert cursor is None and len(seen) == 75
    item_id = next(iter(seen))
    response = client.patch(
        f"/api/v1/feeds/items/{item_id}",
        json={"pinned": True, "rank_override": 99, "editorial_status": "SELECTED"},
    )
    assert response.status_code == 200
    assert candidates(client, status="all")["items"][0]["id"] == item_id
    assert candidates(client, status="SELECTED")["total"] == 1
    assert candidates(client, source_id=source["id"], category="Bangladesh")["total"] == 74
    assert candidates(client, query="nonexistent")["total"] == 0
    client.patch("/api/v1/ingestion/settings", json={"candidate_limit": 50})
    assert len(candidates(client)["items"]) == 50
    assert client.get("/api/v1/feeds/items?cursor=invalid").status_code == 422
    assert client.patch(f"/api/v1/feeds/items/{item_id}", json={"pinned": None}).status_code == 422


def test_source_permissions_activation_unsupported_formats_and_auth(newsroom):
    client, _, web = newsroom
    assert client.get("/api/v1/sources", headers={"Authorization": "Bearer bad"}).status_code == 401
    for url in [
        "http://127.0.0.1/feed",
        "file:///etc/passwd",
        "https://user:secret@publisher.example/rss",
    ]:
        assert (
            client.post("/api/v1/sources", json={"publisher": "Bad", "url": url}).status_code == 422
        )
    assert (
        client.post(
            "/api/v1/sources", json={"publisher": "", "url": "https://news.example/"}
        ).status_code
        == 422
    )
    reference = add_source(client, source_type="manual")
    assert client.post(f"/api/v1/sources/{reference['id']}/collect").status_code == 409
    before = len(web.calls)
    assert (
        client.post(f"/api/v1/sources/{reference['id']}/test").json()["health"] == "REFERENCE_ONLY"
    )
    assert len(web.calls) == before
    source = add_source(client, publisher="Blocked", rights="prohibited")
    assert client.post(f"/api/v1/sources/{source['id']}/collect").status_code == 409
    web.documents["https://api.example/news"] = Document(
        "https://api.example/news", 200, b'{"news": []}', {}
    )
    tested = client.post(
        "/api/v1/sources/test", json={"url": "https://api.example/news", "source_type": "api"}
    )
    assert tested.status_code == 200 and not tested.json()["supported"]
    assert "adapter" in tested.json()["message"]
    normal = add_source(client, active=False)
    assert client.post(f"/api/v1/sources/{normal['id']}/collect").status_code == 409
    assert (
        client.patch(
            f"/api/v1/sources/{normal['id']}", json={"active": True, "polling_interval": 5}
        ).status_code
        == 200
    )
    assert (
        client.patch(f"/api/v1/sources/{normal['id']}", json={"polling_interval": 1}).status_code
        == 422
    )
    assert collect(client, normal)["status"] == "SUCCEEDED"


def test_conditional_requests_and_not_modified_preserve_metadata(newsroom):
    client, factory, web = newsroom
    source = add_source(client)
    collect(client, source)
    web.documents[source["url"]] = Document(source["url"], 304, b"", {})
    assert "304" in collect(client, source)["message"]
    assert web.calls[-1][1]["If-None-Match"] == "v1"
    assert "If-Modified-Since" in web.calls[-1][1]
    assert candidates(client)["total"] == 1
    with factory() as session:
        assert session.scalar(select(Feed.last_success)) is not None


def test_failure_backoff_and_source_disabled_during_fetch(newsroom):
    client, factory, web = newsroom
    source = add_source(client)
    web.documents[source["url"]] = SourceError("Rate limited", retry_after=3600)
    assert collect(client, source)["status"] == "FAILED"
    with factory() as session:
        row = session.get(Source, uuid.UUID(source["id"]))
        assert row.failure_count == 1 and row.health == "ERROR"
        assert service.aware(row.next_collection_at) > now() + timedelta(minutes=59)
    web.documents[source["url"]] = rss()

    def deactivate():
        with factory() as session:
            row = session.get(Source, uuid.UUID(source["id"]))
            row.active = False
            session.commit()

    web.on_fetch = deactivate
    assert collect(client, source)["status"] == "FAILED"
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(IngestedItem)) == 0


def test_scheduler_reserves_only_due_collectible_sources_and_recovers_abandoned_jobs(
    newsroom, monkeypatch
):
    client, factory, _ = newsroom
    active = add_source(client, polling_interval=5)
    add_source(client, active=False)
    add_source(client, source_type="manual")
    add_source(client, extraction_mode="reference_only")
    add_source(client, rights="prohibited")
    with factory() as session:
        jobs = tasks.reserve_due(session)
        assert len(jobs) == 1
        assert tasks.reserve_due(session) == []
        source = session.get(Source, uuid.UUID(active["id"]))
        assert service.aware(source.next_collection_at) >= now() + timedelta(minutes=4, seconds=59)
        run = session.get(CollectionRun, jobs[0])
        run.updated_at = now() - timedelta(minutes=11)
        source.collection_lock_id = run.id
        source.locked_until = now() - timedelta(minutes=1)
        session.commit()
        assert len(tasks.reserve_due(session)) == 1
        assert session.get(CollectionRun, jobs[0]).status == "FAILED"


def test_duplicate_delivery_does_not_collect_under_an_existing_lease(newsroom):
    client, factory, web = newsroom
    source = add_source(client)
    with factory() as session:
        run = CollectionRun(source_id=uuid.UUID(source["id"]), status="RUNNING")
        session.add(run)
        session.flush()
        row = session.get(Source, uuid.UUID(source["id"]))
        row.collection_lock_id, row.locked_until = run.id, now() + timedelta(minutes=5)
        session.commit()
        run_id = run.id
    assert collect_run(run_id, factory)["status"] == "already_running"
    assert not web.calls


def test_json_feed_atom_and_hostile_xml():
    payload = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": "JSON News",
        "items": [
            {
                "id": "one",
                "url": "https://publisher.example/one",
                "title": "JSON item",
                "summary": "An excerpt",
                "date_published": "2026-10-19T07:00:00+06:00",
            },
            {"id": "two", "title": "Missing URL"},
        ],
    }
    result = parse_feed(
        Document("https://publisher.example/feed", 200, json.dumps(payload).encode(), {})
    )
    assert len(result.articles) == 1 and result.skipped == 1
    assert result.articles[0].published_at == datetime(2026, 10, 19, 1, tzinfo=UTC)
    atom = b"""<feed xmlns="http://www.w3.org/2005/Atom">
      <title>Atom</title><id>urn:feed</id><updated>2026-10-19T01:00:00Z</updated>
      <entry><id>urn:one</id><title>Atom item</title>
      <link href="https://publisher.example/atom"/>
      <summary>&lt;script&gt;bad()&lt;/script&gt;Safe summary</summary>
      <updated>2026-10-19T01:00:00Z</updated></entry></feed>"""
    item = parse_feed(Document("https://publisher.example/atom.xml", 200, atom, {})).articles[0]
    assert item.title == "Atom item" and "bad()" not in item.excerpt
    for content in [b"<rss><bad>", b'<!DOCTYPE rss [<!ENTITY x "boom">]><rss>&x;</rss>']:
        with pytest.raises(SourceError):
            parse_feed(Document("https://publisher.example/feed", 200, content, {}))
    unadvertised = FakeWeb()
    unadvertised.documents["https://publisher.example/"] = Document(
        "https://publisher.example/", 200, b"<html>No feed advertised</html>", {}
    )
    result = probe(
        SimpleNamespace(
            source_type="website",
            extraction_mode="metadata",
            rights="metadata_only",
            feed_url=None,
            url="https://publisher.example/",
        ),
        unadvertised,
    )
    assert not result["supported"] and "No advertised" in result["message"]


def test_worker_imports_resolve_foreign_keys_without_importing_the_api():
    script = (
        "from app.ingestion.tasks import collect_source; "
        "from app.db.base import Base; "
        "assert all(fk.column is not None for table in Base.metadata.tables.values() "
        "for fk in table.foreign_keys)"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr


def test_disabled_or_non_editor_identity_cannot_use_source_routes(newsroom):
    client, factory, _ = newsroom
    add_source(client)
    with factory() as session:
        user = session.get(User, EDITOR_ID)
        user.active = False
        session.commit()
    assert client.get("/api/v1/sources").status_code == 403
    with factory() as session:
        user = session.get(User, EDITOR_ID)
        user.active, user.role = True, "viewer"
        session.commit()
    assert (
        client.post(
            "/api/v1/sources/test", json={"url": "https://publisher.example/feed"}
        ).status_code
        == 403
    )


def test_unexpected_worker_failures_leave_a_terminal_observable_job(newsroom, monkeypatch):
    client, factory, _ = newsroom
    source = add_source(client)
    with factory() as session:
        run = CollectionRun(source_id=uuid.UUID(source["id"]))
        session.add(run)
        session.commit()
        run_id = run.id

    def crash(*args, **kwargs):
        raise RuntimeError("unexpected worker fault")

    monkeypatch.setattr(tasks, "collect_run", crash)
    with pytest.raises(RuntimeError):
        tasks.collect_source.run(str(run_id))
    job = client.get(f"/api/v1/ingestion/jobs/{run_id}").json()
    assert job["status"] == "FAILED" and "retry" in job["message"]


def test_feed_declared_original_publisher_is_carried_into_the_draft(newsroom):
    client, _, web = newsroom
    document = rss()
    document.body = document.body.replace(
        b"<category>",
        b'<source url="https://wire.example/feed">Original wire agency</source><category>',
    )
    web.documents["https://publisher.example/feed"] = document
    source = add_source(client, publisher="RSS aggregator")
    collect(client, source)
    item = candidates(client)["items"][0]
    assert item["publisher"] == "Original wire agency"
    draft = client.post(f"/api/v1/feeds/items/{item['id']}/draft").json()
    assert draft["credits"][0]["publisher_name"] == "Original wire agency"
    assert draft["credits"][0]["original_url"].startswith("https://publisher.example/story/0")


def test_invalid_json_feed_metadata_is_skipped_without_crashing():
    payload = {
        "version": "https://jsonfeed.org/version/1.1",
        "items": [
            {
                "id": "bad-author",
                "url": "https://publisher.example/one",
                "title": "One",
                "authors": {"name": "Wrong container type"},
            },
            {
                "id": "bad-tags",
                "url": "https://publisher.example/two",
                "title": "Two",
                "tags": "Wrong container type",
            },
            {
                "id": "good",
                "url": "https://publisher.example/three",
                "title": "Three",
                "date_published": 12345,
            },
        ],
    }
    result = parse_feed(
        Document("https://publisher.example/feed", 200, json.dumps(payload).encode(), {})
    )
    assert result.skipped == 2 and len(result.articles) == 1
    assert result.articles[0].published_at is None
    payload["version"] = []
    with pytest.raises(SourceError, match="adapter"):
        parse_feed(
            Document("https://publisher.example/feed", 200, json.dumps(payload).encode(), {})
        )


def test_new_incoming_items_do_not_duplicate_candidates_between_batches(newsroom):
    client, _, web = newsroom
    source = add_source(client)
    web.documents[source["url"]] = rss(60)
    collect(client, source)
    client.patch("/api/v1/ingestion/settings", json={"candidate_limit": 20})
    first = candidates(client)
    web.documents[source["url"]] = rss(61)
    collect(client, source)
    fresh = candidates(client, query="River report 60")["items"][0]
    client.patch(f"/api/v1/feeds/items/{fresh['id']}", json={"pinned": True})
    second = candidates(client, cursor=first["next_cursor"])
    assert len(second["items"]) == 20
    assert not ({item["id"] for item in first["items"]} & {item["id"] for item in second["items"]})
    assert (
        client.get(
            "/api/v1/feeds/items", params={"cursor": first["next_cursor"], "status": "SELECTED"}
        ).status_code
        == 422
    )
