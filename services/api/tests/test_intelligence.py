import json
import uuid
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.ingestion.models import Feed, IngestedItem, Source
from app.ingestion.network import Document, SourceError
from app.ingestion.parsing import ParsedFeed, article
from app.ingestion.service import ingest, now
from app.intelligence.analytics import attach, measure, similarity
from app.intelligence.classification import classify, controls, deterministic, fingerprint, reserve
from app.intelligence.models import (
    IntelligenceUsage,
    ItemAnalysis,
    TrendSnapshot,
)
from app.intelligence.providers import GDELT, GoogleTrends, Instagram
from app.intelligence.provision import provision
from app.intelligence.schemas import Classification, Controls
from app.intelligence.tasks import run_cycle
from tests.test_accounts_workflow import accounts  # noqa: F401
from tests.test_ingestion import newsroom  # noqa: F401


def seeded(
    factory,
    *,
    title="Bangladesh cyclone response begins along coast",
    publisher="Publisher",
    url=None,
    source_type="rss",
):
    with factory() as s:
        source = Source(
            publisher=publisher,
            url="https://publisher.example/feed",
            homepage="https://publisher.example/",
            language="en",
            rights="metadata_only",
            source_type=source_type,
            active=True,
        )
        s.add(source)
        s.flush()
        feed = Feed(source_id=source.id, url=source.url)
        s.add(feed)
        s.flush()
        item = article(
            uuid.uuid4().hex,
            url or f"https://publisher.example/{uuid.uuid4()}",
            title,
            "Permitted headline summary about response operations",
            published_at=now(),
            publisher_name=publisher,
        )
        ingest(s, source, feed, ParsedFeed(publisher, [item]))
        s.commit()
        candidate = s.scalar(
            select(IngestedItem).where(IngestedItem.normalized_url == item.normalized_url)
        )
        return candidate.id, source.id


def test_discovery_to_classification_cluster_recommendation_and_existing_draft(  # noqa: F811
    newsroom,  # noqa: F811
    monkeypatch,  # noqa: F811
):  # noqa: F811
    client, factory, web = newsroom
    # Collection uses the real service with the fixture's bounded RSS response.
    response = client.post(
        "/api/v1/sources",
        json={
            "publisher": "RSS publisher",
            "active": True,
            "url": "https://publisher.example/feed",
            "language": "bn",
        },
    )
    assert response.status_code == 201, response.text
    assert client.post(f"/api/v1/sources/{response.json()['id']}/collect").status_code == 202
    with factory() as s:
        item = s.scalar(select(IngestedItem))
        item.category = ""
        item_id = item.id
        row, config = controls(s)
        row.config = {
            **config.model_dump(),
            "automatic_classification": True,
            "model": "test-classifier",
        }
        s.commit()
    env = get_settings()
    for key, value in {
        "openai_api_key": "test-only",
        "openai_classification_model": "test-classifier",
        "openai_classification_input_per_million": 0.1,
        "openai_classification_output_per_million": 0.5,
    }.items():
        monkeypatch.setattr(env, key, value)
    result = Classification(
        primary_category="Bangladesh",
        secondary_category=None,
        tags=["river"],
        topic_keywords=["river", "report"],
        entities=[],
        geography=["BD"],
        bangladesh_relevance=90,
        public_interest=80,
        confidence=0.8,
        evidence_limitations=["Metadata only"],
    )
    calls = []

    def provider(request):
        calls.append(request)
        assert json.loads(request.content)["store"] is False
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": result.model_dump_json()}],
                    }
                ],
                "usage": {"input_tokens": 100, "output_tokens": 100},
            },
        )

    assert classify(factory, item_id, allow_ai=True, transport=httpx.MockTransport(provider))
    assert not classify(factory, item_id, allow_ai=True, transport=httpx.MockTransport(provider))
    assert len(calls) == 1
    monkeypatch.setattr("app.intelligence.classification.PROMPT_VERSION", "test-next-version")
    assert classify(factory, item_id, allow_ai=True, transport=httpx.MockTransport(provider))
    assert len(calls) == 2
    run_cycle(factory, force=True)
    response = client.get("/api/v1/intelligence/recommendations?geography=BD")
    assert response.status_code == 200, response.text
    trend = response.json()["items"][0]
    assert trend["signals"]["independent_confirmations"] is None
    assert trend["signals"]["google_trends"] is None
    assert trend["sources"][0]["publisher"] == "RSS publisher"
    draft = client.post(f"/api/v1/intelligence/trends/{trend['id']}/draft")
    assert draft.status_code == 200, draft.text
    assert draft.json()["status"] == "DRAFT"
    assert draft.json()["tags"] == ["river"]
    again = client.post(f"/api/v1/intelligence/trends/{trend['id']}/draft")
    assert draft.json()["id"] == again.json()["id"]
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(TrendSnapshot)) == 4
        usage = s.scalar(select(IntelligenceUsage))
        assert usage.status == "SUCCEEDED" and float(usage.cost_usd) > 0


def test_editorial_overrides_split_merge_filters_and_permissions(accounts):  # noqa: F811
    admin, factory, _, clients = accounts
    first, _ = seeded(factory)
    second, _ = seeded(
        factory, title="Bangladesh cyclone response begins along coast today", publisher="Other"
    )
    run_cycle(factory, force=True)
    trends = admin.get("/api/v1/intelligence/trends").json()["items"]
    assert len(trends) == 1
    cid = trends[0]["id"]
    writer, editor = clients["writer"], clients["editor"]
    assert (
        writer.patch(f"/api/v1/intelligence/trends/{cid}", json={"score_override": 99}).status_code
        == 403
    )
    assert (
        editor.patch("/api/v1/intelligence/settings", json={"daily_budget_usd": 3}).status_code
        == 403
    )
    assert (
        editor.post(
            "/api/v1/sources", json={"publisher": "No", "url": "https://publisher.example/"}
        ).status_code
        == 403
    )
    assert (
        editor.patch(
            f"/api/v1/intelligence/items/{first}/classification",
            json={"primary_category": "Technology", "tags": ["human"]},
        ).status_code
        == 200
    )
    assert (
        editor.patch(
            f"/api/v1/intelligence/trends/{cid}", json={"score_override": 99, "pinned": True}
        ).status_code
        == 200
    )
    result = editor.post(
        f"/api/v1/intelligence/trends/{cid}/move", json={"item_ids": [str(second)]}
    )
    assert result.status_code == 200, result.text
    target = result.json()["id"]
    assert len(admin.get("/api/v1/intelligence/trends").json()["items"]) == 2
    assert (
        editor.post(
            f"/api/v1/intelligence/trends/{target}/move",
            json={"item_ids": [str(second)], "target_cluster_id": cid},
        ).status_code
        == 200
    )
    with factory() as s:
        item = s.get(IngestedItem, first)
        item.excerpt = "Changed permitted summary"
        s.commit()
    classify(factory, first)
    with factory() as s:
        analysis = s.scalar(select(ItemAnalysis).where(ItemAnalysis.item_id == first))
        assert analysis.editorial_override["tags"] == ["human"]
    assert admin.get("/api/v1/intelligence/trends?query=nomatch").json()["total"] == 0
    assert admin.get("/api/v1/intelligence/trends?category=Sports").json()["total"] == 0
    assert admin.get("/api/v1/intelligence/trends?window=invalid").status_code == 422


def test_instagram_registration_manual_link_dedup_and_rights(accounts):  # noqa: F811
    admin, factory, _, clients = accounts
    body = {
        "publisher": "IG reporting",
        "url": "https://www.instagram.com/newsroom/",
        "source_type": "INSTAGRAM_ACCOUNT",
        "provider_config": {"username": "newsroom"},
    }
    assert clients["writer"].post("/api/v1/sources", json=body).status_code == 403
    r = admin.post("/api/v1/sources", json=body)
    assert r.status_code == 201, r.text
    assert not r.json()["active"]
    path = f"/api/v1/intelligence/sources/{r.json()['id']}/instagram-post"
    lead = {
        "url": "https://www.instagram.com/p/Abcd123/",
        "title": "Public-interest reporting lead",
    }
    assert clients["writer"].post(path, json=lead).status_code == 403
    assert clients["editor"].post(path, json=lead).json()["inserted"] == 1
    assert clients["editor"].post(path, json=lead).json()["duplicates"] == 1
    assert (
        admin.post(path, json={**lead, "url": "https://evil.example/p/Abcd123/"}).status_code == 422
    )
    admin.patch(f"/api/v1/sources/{r.json()['id']}", json={"rights": "prohibited"})
    assert admin.post(path, json=lead).status_code == 403


def test_provisioning_never_changes_administrator_sources(newsroom):  # noqa: F811
    _, factory, _ = newsroom
    with factory() as s:
        created = provision(s)
        assert created
        source = s.scalar(select(Source).where(Source.provision_key == "tbs"))
        source.notes, source.polling_interval = "Admin choice", 77
        s.commit()
        assert provision(s) == []
        s.refresh(source)
        assert source.notes == "Admin choice" and source.polling_interval == 77
        assert all(not r.active for r in s.scalars(select(Source)))


def test_budget_reservation_cache_and_no_unknown_price_calls(newsroom, monkeypatch):  # noqa: F811
    _, factory, _ = newsroom
    item_id, _ = seeded(factory)
    env = get_settings()
    for key, value in {
        "openai_api_key": "test",
        "openai_classification_model": "cheap",
        "openai_classification_input_per_million": 1,
        "openai_classification_output_per_million": 1,
    }.items():
        monkeypatch.setattr(env, key, value)
    with factory() as s:
        row, config = controls(s)
        row.config = {
            **config.model_dump(),
            "automatic_classification": True,
            "model": "cheap",
            "daily_budget_usd": 0.001,
        }
        s.commit()
        _, config = controls(s)
        item = s.get(IngestedItem, item_id)
        assert reserve(s, item, config, fingerprint(item, config)) is None
        row.config = {**config.model_dump(), "daily_budget_usd": 1}
        s.commit()
        _, config = controls(s)
        usage = reserve(s, item, config, fingerprint(item, config))
        assert usage and float(usage.reserved_usd) > 0
        s.commit()
        assert reserve(s, item, config, fingerprint(item, config)) is None
        assert reserve(s, item, config, "different") is None  # In-flight concurrency cap.
        monkeypatch.setattr(env, "openai_classification_input_per_million", 0)
        assert reserve(s, item, config, "different") is None


def test_windows_syndication_missing_signals_and_bilingual_rules(newsroom):  # noqa: F811
    _, factory, _ = newsroom
    first, _ = seeded(factory)
    seeded(
        factory,
        publisher="Syndicated",
        url=None,
        title="Different unrelated public-interest report",
    )
    with factory() as s:
        item = s.get(IngestedItem, first)
        _, config = controls(s)
        data, sufficient = deterministic(
            SimpleNamespace(title="ঢাকায় হাসপাতাল ও স্বাস্থ্য সেবা", excerpt="", category="", language="bn"),
            config,
        )
        assert sufficient and data["primary_category"] == "Health"
        assert data["bangladesh_relevance"] >= 60
        cluster = attach(s, item)
        at = now()
        for window in ("1h", "6h", "24h", "7d"):
            result = measure(s, cluster, window, at=at)
            assert 0 <= result["score"] <= 100
            assert result["signals"]["count"] == 1
            assert result["signals"]["google_trends"] is None
        assert similarity("District flood kills 12 people", "District flood kills 42 people") == 0
        s.commit()
    assert GoogleTrends().status()["status"] == "UNCONFIGURED"


@pytest.mark.parametrize("taxonomy", [["Health", "health"], ["World", " World "], ["", "World"]])
def test_taxonomy_duplicates_rejected(taxonomy):
    with pytest.raises(ValueError):
        Controls(taxonomy=taxonomy)


def test_public_provider_parsers_and_instagram_permission_errors():
    class Fetcher:
        def fetch(self, url):
            return Document(
                url,
                200,
                json.dumps(
                    {
                        "articles": [
                            {
                                "url": "https://publisher.example/news",
                                "title": "Bangladesh response",
                                "domain": "publisher.example",
                                "seendate": "20261021T120000Z",
                            }
                        ]
                    }
                ).encode(),
                {},
            )

    source = SimpleNamespace(provider_config={"query": "Bangladesh"})
    batch = GDELT().collect(source, Fetcher())
    assert batch.feed.articles[0].publisher_name == "publisher.example"
    assert "query=Bangladesh" in batch.document.url
    with pytest.raises(SourceError, match="unconfigured"):
        Instagram().collect(SimpleNamespace())


def test_quota_error_suspends_optional_processing(newsroom, monkeypatch):  # noqa: F811
    _, factory, _ = newsroom
    item_id, _ = seeded(factory)
    env = get_settings()
    for key, value in {
        "openai_api_key": "test",
        "openai_classification_model": "cheap",
        "openai_classification_input_per_million": 0.1,
        "openai_classification_output_per_million": 0.5,
    }.items():
        monkeypatch.setattr(env, key, value)
    with factory() as s:
        row, config = controls(s)
        row.config = {**config.model_dump(), "automatic_classification": True, "model": "cheap"}
        s.commit()
    classify(
        factory,
        item_id,
        allow_ai=True,
        transport=httpx.MockTransport(lambda _: httpx.Response(429)),
    )
    with factory() as s:
        _, config = controls(s)
        assert config.paused
        usage = s.scalar(select(IntelligenceUsage))
        assert usage.status == "FAILED" and usage.cost_usd is None


def test_instagram_pagination_watermarks_and_credentials(monkeypatch):
    env = get_settings()
    monkeypatch.setattr(env, "meta_instagram_token", "test-meta-token")
    monkeypatch.setattr(env, "meta_instagram_account_id", "12345")
    source = SimpleNamespace(
        url="https://www.instagram.com/newsroom/",
        provider_config={"username": "newsroom"},
        provider_cursor={"since": "2026-10-20T00:00:00+00:00"},
    )
    calls = []

    def meta(request):
        calls.append(request)
        assert request.url.host == "graph.facebook.com"
        assert request.headers["authorization"] == "Bearer test-meta-token"
        after = ".after(NEXT_123)" in request.url.params["fields"]
        return httpx.Response(
            200,
            json={
                "business_discovery": {
                    "username": "newsroom",
                    "id": "999",
                    "media": {
                        "data": [
                            {
                                "id": "post-one",
                                "permalink": "https://www.instagram.com/p/Abc123/",
                                "caption": "Public reporting lead",
                                "media_type": "IMAGE",
                                "timestamp": "2026-10-19T00:00:00Z"
                                if after
                                else "2026-10-21T00:00:00Z",
                                "like_count": 12,
                            }
                        ],
                        "paging": {
                            "next": "https://untrusted.example/never-follow",
                            "cursors": {"after": "NEXT_123"},
                        },
                    },
                }
            },
        )

    batch = Instagram().collect(source, transport=httpx.MockTransport(meta))
    assert len(batch.feed.articles) == 1
    assert batch.cursor["after"] == "NEXT_123"
    source.provider_cursor = batch.cursor
    batch = Instagram().collect(source, transport=httpx.MockTransport(meta))
    assert batch.feed.articles and not batch.cursor["after"]
    assert batch.cursor["since"].startswith("2026-10-21")
    assert len(calls) == 2


@pytest.mark.parametrize("status", [403, 429])
def test_instagram_permissions_and_backoff(monkeypatch, status):
    monkeypatch.setattr(get_settings(), "meta_instagram_token", "test-token")
    monkeypatch.setattr(get_settings(), "meta_instagram_account_id", "12345")
    source = SimpleNamespace(
        url="https://www.instagram.com/newsroom/",
        provider_config={"username": "newsroom"},
        provider_cursor={},
    )
    with pytest.raises(SourceError) as error:
        Instagram().collect(source, transport=httpx.MockTransport(lambda _: httpx.Response(status)))
    assert error.value.retry_after == (900 if status == 429 else None)


def test_gdelt_empty_and_invalid_responses():
    class Fetcher:
        def __init__(self, body):
            self.body = body

        def fetch(self, url):
            return Document(url, 200, self.body, {})

    source = SimpleNamespace(provider_config={})
    assert GDELT().collect(source, Fetcher(b'{"articles":[]}')).feed.articles == []
    with pytest.raises(SourceError):
        GDELT().collect(source, Fetcher(b'{"error":"unavailable"}'))


def test_rights_rechecked_before_classification(newsroom):  # noqa: F811
    _, factory, _ = newsroom
    iid, sid = seeded(factory)
    with factory() as session:
        source = session.get(Source, sid)
        source.rights = "prohibited"
        session.commit()
    assert classify(factory, iid, allow_ai=True) is False
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(IntelligenceUsage)) == 0
