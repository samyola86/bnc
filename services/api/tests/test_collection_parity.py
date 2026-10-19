import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.v1 import ingestion as routes
from app.config import get_settings
from app.db.session import get_session
from app.editorial.models import AuditEvent, Story, StorySource
from app.ingestion import service, tasks
from app.ingestion.models import CollectionRun, FeedEntry, IngestedItem, Source
from app.ingestion.service import collect_run, now
from app.main import app
from tests.test_ai_stories import save_payload
from tests.test_ingestion import FakeWeb, add_source, collect, newsroom, rss  # noqa: F401
from tests.test_ingestion_postgres import postgres  # noqa: F401


def exercise_settings_and_archive(client, factory, web):
    add_source(client, polling_interval=45)
    response = client.patch(
        "/api/v1/ingestion/settings",
        json={
            "candidate_limit": 20,
            "default_interval": 60,
            "draft_language": "en",
            "preferred_categories": ["Environment"],
            "source_mode": "all_supported",
            "automatic_collection": True,
        },
    )
    assert response.status_code == 200, response.text
    assert client.get("/api/v1/ingestion/settings").json()["default_interval"] == 60
    assert client.get("/api/v1/sources").json()["items"][0]["polling_interval"] == 45
    source = add_source(client, publisher="New source", url="https://second.example/feed")
    assert source["polling_interval"] == 60
    web.documents[source["url"]] = rss(2)
    assert collect(client, source)["inserted"] == 2
    candidate = client.get("/api/v1/feeds/items").json()["items"][0]
    path = f"/api/v1/feeds/items/{candidate['id']}/draft"
    draft = client.post(path).json()
    assert draft["language"] == "en" and client.post(path).json()["id"] == draft["id"]
    saved = client.patch(
        f"/api/v1/stories/{draft['id']}",
        json=save_payload(
            draft, category="Environment", tags=["Water", "Local"], title="Edited water report"
        ),
    ).json()
    queue = client.get(
        "/api/v1/feeds/items?status=DRAFT&category=Environment&preferred_only=true&query=Edited"
    ).json()
    assert queue["total"] == 1 and queue["items"][0]["draft_category"] == "Environment"
    assert queue["items"][0]["tags"] == ["Water", "Local"]
    assert queue["items"][0]["assigned_author"]["name"]
    archived = client.post(f"/api/v1/sources/{source['id']}/archive")
    assert archived.status_code == 200 and archived.json()["archived_at"]
    assert client.get("/api/v1/sources").json()["total"] == 1
    assert client.get("/api/v1/sources?include_archived=true").json()["total"] == 2
    # Existing API defaults still hide inactive sources; the table explicitly opts into history.
    assert client.get("/api/v1/feeds/items?status=all").json()["total"] == 0
    history = client.get(
        f"/api/v1/feeds/items?status=all&include_inactive=true&source_id={source['id']}"
    ).json()
    assert history["total"] == 2 and history["items"][0]["sources"][0]["archived"]
    assert client.get(f"/api/v1/stories/{draft['id']}").json()["provenance"] == draft["provenance"]
    assert client.post(f"/api/v1/sources/{source['id']}/collect").status_code == 409
    assert client.patch(f"/api/v1/sources/{source['id']}", json={"active": True}).status_code == 409
    restored = client.post(f"/api/v1/sources/{source['id']}/restore").json()
    assert restored["archived_at"] is None and not restored["active"]
    assert client.patch(f"/api/v1/sources/{source['id']}", json={"active": True}).status_code == 200
    missing = client.patch(
        f"/api/v1/stories/{draft['id']}", json=save_payload(saved, credits=[])
    ).json()
    assert (
        missing["warnings"] == ["Missing source credit"]
        and not missing["attribution_blocks_publishing"]
    )
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Story)) == 1
        assert session.scalar(select(func.count()).select_from(FeedEntry)) == 2
        assert session.scalar(select(func.count()).select_from(StorySource)) == 2
        assert session.scalar(select(AuditEvent).where(AuditEvent.action == "source.archived"))
    assert client.get("/api/v1/sources?cursor=invalid").status_code == 422


def test_settings_archive_editorial_metadata_and_nonblocking_credits(newsroom):  # noqa: F811
    exercise_settings_and_archive(*newsroom)


def test_postgres_collection_settings_archive_and_editorial_metadata(postgres, monkeypatch):  # noqa: F811
    factory, web = postgres, FakeWeb()

    def sessions():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    monkeypatch.setattr(get_settings(), "ingestion_api_token", "test-editor-token")
    monkeypatch.setattr(service, "SafeFetcher", lambda: web)
    monkeypatch.setattr(routes, "enqueue", lambda run_id: bool(collect_run(run_id, factory)))
    try:
        with TestClient(app, headers={"Authorization": "Bearer test-editor-token"}) as client:
            exercise_settings_and_archive(client, factory, web)
    finally:
        app.dependency_overrides.clear()


def test_scheduler_policy_modes_pause_and_manual_collection(newsroom):  # noqa: F811
    client, factory, web = newsroom
    direct = add_source(client)
    website = add_source(
        client,
        publisher="Website",
        source_type="website",
        url="https://website.example/",
        feed_url="https://publisher.example/feed",
    )
    client.patch("/api/v1/ingestion/settings", json={"automatic_collection": False})
    with factory() as session:
        assert tasks.reserve_due(session) == []
    assert collect(client, direct)["inserted"] == 1  # Explicit manual runs still work.
    client.patch(
        "/api/v1/ingestion/settings",
        json={"automatic_collection": True, "source_mode": "feeds_only"},
    )
    with factory() as session:
        session.get(Source, uuid.UUID(direct["id"])).next_collection_at = now() - timedelta(
            minutes=1
        )
        session.commit()
        jobs = tasks.reserve_due(session)
        assert len(jobs) == 1
        run = session.get(CollectionRun, jobs[0])
        assert run.source_id == uuid.UUID(direct["id"]) and run.trigger == "scheduled"
    client.patch("/api/v1/ingestion/settings", json={"automatic_collection": False})
    calls = len(web.calls)
    assert collect_run(jobs[0], factory)["status"] == "SKIPPED"
    assert len(web.calls) == calls
    assert collect(client, website)["duplicates"] == 1


def test_pause_during_scheduled_fetch_discards_results_without_source_failure(newsroom):  # noqa: F811
    client, factory, web = newsroom
    source = add_source(client)
    with factory() as session:
        jobs = tasks.reserve_due(session)
    web.on_fetch = lambda: client.patch(
        "/api/v1/ingestion/settings", json={"automatic_collection": False}
    )
    assert collect_run(jobs[0], factory)["status"] == "SKIPPED"
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(IngestedItem)) == 0
        saved = session.get(Source, uuid.UUID(source["id"]))
        assert saved.failure_count == 0 and saved.collection_lock_id is None


def test_manual_refresh_reuses_pending_scheduled_work_when_automatic_is_paused(newsroom):  # noqa: F811
    client, factory, _ = newsroom
    source = add_source(client)
    with factory() as session:
        jobs = tasks.reserve_due(session)
    client.patch("/api/v1/ingestion/settings", json={"automatic_collection": False})
    response = client.post(f"/api/v1/sources/{source['id']}/collect")
    assert response.status_code == 202 and response.json()["job_id"] == str(jobs[0])
    with factory() as session:
        assert session.get(CollectionRun, jobs[0]).trigger == "manual"
    assert collect_run(jobs[0], factory)["status"] == "SUCCEEDED"


def test_source_draft_language_overrides_global_without_changing_feed(newsroom):  # noqa: F811
    client, _, _ = newsroom
    client.patch("/api/v1/ingestion/settings", json={"draft_language": "en"})
    source = add_source(client, language="en", draft_language="bn")
    collect(client, source)
    item = client.get("/api/v1/feeds/items").json()["items"][0]
    draft = client.post(f"/api/v1/feeds/items/{item['id']}/draft").json()
    assert draft["language"] == "bn" and item["language"] == "en"
    assert (
        client.post("/api/v1/stories", json={"title": "Global language"}).json()["language"] == "en"
    )
    assert (
        client.post("/api/v1/stories", json={"title": "Override", "language": "bn"}).json()[
            "language"
        ]
        == "bn"
    )


@pytest.mark.parametrize(
    "body",
    [
        {"candidate_limit": 19},
        {"default_interval": 4},
        {"automatic_collection": None},
        {"draft_language": "fr"},
        {"source_mode": "scrape_all"},
        {"preferred_categories": [" "]},
        {"invented_setting": True},
    ],
)
def test_invalid_settings_are_rejected(newsroom, body):  # noqa: F811
    client, _, _ = newsroom
    assert client.patch("/api/v1/ingestion/settings", json=body).status_code == 422


def test_database_summary_counts_and_unavailable_publishing(newsroom):  # noqa: F811
    client, _, web = newsroom
    source = add_source(client)
    web.documents[source["url"]] = rss(3)
    collect(client, source)
    client.post("/api/v1/stories", json={"title": "Original reporting"})
    before = client.get("/api/v1/feeds/summary").json()
    assert before["incoming"]["count"] == 3 and before["original_drafts"]["count"] == 1
    item = client.get("/api/v1/feeds/items").json()["items"][0]
    client.post(f"/api/v1/feeds/items/{item['id']}/draft")
    after = client.get("/api/v1/feeds/summary").json()
    assert after["incoming"]["count"] == 2 and after["original_drafts"]["count"] == 1
    assert not after["published"]["available"] and after["published"]["count"] == 0
    assert after["awaiting_publication"]["available"]
    assert client.get("/api/v1/feeds/summary", headers={"Authorization": ""}).status_code == 401


def test_publication_counts_use_distinct_stored_stories(newsroom):  # noqa: F811
    from app.editorial.models import StoryVersion
    from app.publishing.models import Channel, Publication

    client, factory, _ = newsroom
    first = client.post("/api/v1/stories", json={"title": "First"}).json()
    second = client.post("/api/v1/stories", json={"title": "Second"}).json()
    with factory() as session:
        channels = [Channel(type="wordpress"), Channel(type="facebook")]
        session.add_all(channels)
        session.flush()
        first_version = session.scalar(
            select(StoryVersion.id).where(StoryVersion.story_id == uuid.UUID(first["id"]))
        )
        second_version = session.scalar(
            select(StoryVersion.id).where(StoryVersion.story_id == uuid.UUID(second["id"]))
        )
        session.add_all(
            [
                Publication(approved_version_id=first_version, channel_id=c.id, status="CONFIRMED")
                for c in channels
            ]
            + [
                Publication(
                    approved_version_id=second_version, channel_id=channels[0].id, status="PENDING"
                )
            ]
        )
        session.commit()
    summary = client.get("/api/v1/feeds/summary").json()
    assert summary["published"]["count"] == 1
    assert summary["awaiting_publication"]["count"] == 1
    assert not summary["published"]["available"]
