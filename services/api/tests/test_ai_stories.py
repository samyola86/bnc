import json
import uuid
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app.ai import provider, tasks
from app.ai.models import AIJob
from app.ai.provider import GenerationError, generate
from app.api.v1 import stories as routes
from app.config import get_settings
from app.editorial.models import StorySource, StoryVersion
from app.ingestion.service import now
from tests.test_ingestion import add_source, collect, newsroom  # noqa: F401


def generated(source_id="editor-notes", language="bn"):
    return {
        "language": language,
        "headline": "নদীর পানি নিয়ে প্রতিবেদন" if language == "bn" else "River report",
        "summary": "স্থানীয় সংবাদদাতার প্রতিবেদন।",
        "paragraphs": [
            {"text": "নদীর পানি পর্যবেক্ষণ করা হয়েছে।", "supporting_source_ids": [source_id]}
        ],
        "category": "Bangladesh",
        "tags": ["river"],
        "social_captions": {"facebook": "নদীর প্রতিবেদন", "instagram": "নদীর খবর"},
        "claims_to_verify": ["Verify the observation with the reporter"],
        "editorial_warnings": ["Limited source material"],
        "ready_for_review": False,
    }


def envelope(result=None, **extra):
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": json.dumps(result or generated())},
                ],
            }
        ],
        "usage": {"input_tokens": 100, "output_tokens": 80, "total_tokens": 180},
        **extra,
    }


@pytest.fixture
def ai(newsroom, monkeypatch):  # noqa: F811 - imported shared pytest fixture
    client, factory, web = newsroom
    monkeypatch.setattr(get_settings(), "openai_api_key", "test-not-a-real-key")
    monkeypatch.setattr(get_settings(), "openai_model", "test-structured-model")
    monkeypatch.setattr(
        routes, "enqueue", lambda job_id: bool(tasks.run_job(job_id, factory) or True)
    )
    return client, factory, web


def test_responses_request_and_schema(monkeypatch):
    monkeypatch.setattr(get_settings(), "openai_api_key", "test-not-a-real-key")

    def server(request):
        assert request.url == "https://api.openai.com/v1/responses"
        assert request.headers["authorization"] == "Bearer test-not-a-real-key"
        body = json.loads(request.content)
        assert body["model"] == "test-model" and body["store"] is False
        assert body["text"]["format"]["strict"] is True
        assert body["text"]["format"]["schema"]["additionalProperties"] is False
        assert "tools" not in body
        assert "untrusted" in body["instructions"]
        assert json.loads(body["input"])["evidence"][0]["id"] == "editor-notes"
        return httpx.Response(200, json=envelope())

    result, usage = generate(
        {"language": "bn", "evidence": [{"id": "editor-notes"}]},
        "test-model",
        transport=httpx.MockTransport(server),
    )
    assert result["ready_for_review"] is False and usage["total_tokens"] == 180


@pytest.mark.parametrize(
    "status,match",
    [
        (401, "credentials"),
        (403, "credentials"),
        (429, "quota"),
        (503, "unavailable"),
        (400, "Structured"),
    ],
)
def test_provider_errors_are_sanitized(monkeypatch, status, match):
    monkeypatch.setattr(get_settings(), "openai_api_key", "test-not-a-real-key")
    with pytest.raises(GenerationError, match=match) as exc:
        generate(
            {},
            "test-model",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(status, text="sensitive-provider-error")
            ),
        )
    assert "sensitive-provider-error" not in str(exc.value)


@pytest.mark.parametrize(
    "bad",
    [
        "incomplete",
        "refusal",
        "invalid-json",
        "unknown-source",
        "language",
        "extra-field",
        "approval",
        "no-evidence",
    ],
)
def test_invalid_responses_never_become_drafts(monkeypatch, bad):
    monkeypatch.setattr(get_settings(), "openai_api_key", "test-not-a-real-key")
    data = envelope()
    if bad == "incomplete":
        data["status"] = "incomplete"
    elif bad == "refusal":
        data["output"][0]["content"] = [{"type": "refusal", "refusal": "declined"}]
    elif bad == "invalid-json":
        data["output"][0]["content"][0]["text"] = "not json"
    else:
        result = generated()
        if bad == "unknown-source":
            result["paragraphs"][0]["supporting_source_ids"] = ["invented"]
        elif bad == "language":
            result["language"] = "en"
        elif bad == "extra-field":
            result["sources"] = ["invented"]
        elif bad == "approval":
            result["ready_for_review"] = True
        else:
            result["paragraphs"][0]["supporting_source_ids"] = []
        data = envelope(result)
    with pytest.raises(GenerationError):
        generate(
            {"language": "bn", "evidence": [{"id": "editor-notes"}]},
            "test-model",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data)),
        )


def test_timeout_and_missing_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    with pytest.raises(GenerationError, match="not configured"):
        generate({}, "test-model")
    monkeypatch.setattr(get_settings(), "openai_api_key", "test-not-a-real-key")

    def timeout(request):
        raise httpx.ReadTimeout("sensitive", request=request)

    with pytest.raises(GenerationError, match="timed out"):
        generate({}, "test-model", transport=httpx.MockTransport(timeout))


def save_payload(draft, **extra):
    return {
        "base_version": draft["version"],
        "title": draft["title"],
        "summary": draft["summary"],
        "body": draft["body"],
        "language": draft["language"],
        "credits": [
            {k: v for k, v in credit.items() if k != "entry_method"} for credit in draft["credits"]
        ],
        **extra,
    }


def test_manual_create_edit_list_history_and_nonblocking_credits(ai):
    client, factory, _ = ai
    draft = client.post(
        "/api/v1/stories",
        json={"title": "Manual report", "language": "en", "body": "Original reporting"},
    ).json()
    path = f"/api/v1/stories/{draft['id']}"
    assert draft["origin_item_id"] is None and draft["provenance"] == []
    assert draft["warnings"] == ["Missing source credit"]
    assert draft["attribution_blocks_publishing"] is False
    credit = {
        "publisher_name": "BNC reporter",
        "attribution_text": "Field notes",
        "is_original_reporting": True,
    }
    response = client.patch(
        path,
        json=save_payload(
            draft,
            title="Edited report",
            credits=[credit],
            tags=["river"],
            social_captions={"facebook": "Manual caption"},
        ),
    )
    assert response.status_code == 200, response.text
    saved = client.get(path).json()
    assert saved["version"] == 2 and saved["body"] == "Original reporting"
    assert saved["language"] == "en" and saved["warnings"] == []
    assert saved["tags"] == ["river"] and saved["social_captions"]["facebook"] == "Manual caption"
    assert client.patch(path, json=save_payload(draft)).status_code == 409
    listed = client.get("/api/v1/stories?origin=manual").json()
    assert listed["total"] == 1 and listed["items"][0]["title"] == "Edited report"
    assert client.get("/api/v1/stories?origin=candidate").json()["total"] == 0
    history = client.get(path + "/versions").json()
    assert [v["version"] for v in history["items"]] == [2, 1]
    assert history["items"][1]["content"]["body"] == "Original reporting"
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(StoryVersion)) == 2


@pytest.mark.parametrize("language", ["bn", "en"])
def test_complete_rss_ai_edit_save_workflow(ai, monkeypatch, language):
    client, factory, _ = ai
    source = add_source(client)
    collect(client, source)
    item = client.get("/api/v1/feeds/items").json()["items"][0]
    draft = client.post(f"/api/v1/feeds/items/{item['id']}/draft").json()
    captured = []

    def fake_response(packet, model):
        captured.append(packet)
        return provider.generate(
            packet,
            model,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json=envelope(generated(item["id"], language)))
            ),
        )

    monkeypatch.setattr(tasks, "generate", fake_response)
    path = f"/api/v1/stories/{draft['id']}"
    response = client.post(path + "/ai-draft", json={"base_version": 1, "language": language})
    assert response.status_code == 202, response.text
    job = client.get(f"/api/v1/ai/jobs/{response.json()['job_id']}").json()
    assert job["status"] == "SUCCEEDED", job
    assert captured[0]["evidence"][0]["kind"] == "feed_metadata"
    assert captured[0]["evidence"][0]["attributions"][0]["publisher_name"] == "Original publisher"
    assert "Verified feed excerpt" in captured[0]["evidence"][0]["text"]
    assert client.get(path).json()["version"] == 1  # Preview never silently overwrites.
    result = job["result"]
    response = client.patch(
        path,
        json=save_payload(
            draft,
            title=result["headline"],
            body=result["paragraphs"][0]["text"] + " Human edit.",
            language=language,
            ai_job_id=job["id"],
            tags=result["tags"],
            social_captions=result["social_captions"],
            category=result["category"],
        ),
    )
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["version"] == 2 and saved["status"] == "DRAFT"
    assert saved["human_review_required"] is True and saved["body"].endswith("Human edit.")
    assert saved["language"] == language
    assert [{k: v for k, v in c.items() if k != "entry_method"} for c in saved["credits"]] == [
        {k: v for k, v in c.items() if k != "entry_method"} for c in draft["credits"]
    ]
    assert saved["provenance"] == draft["provenance"]
    queue = client.get("/api/v1/feeds/items?status=DRAFT").json()["items"][0]
    assert queue["tags"] == result["tags"] and queue["draft_category"] == result["category"]
    assert queue["ai_assisted"] is True
    assert client.patch(path, json=save_payload(saved, body="Later human revision")).json()[
        "human_review_required"
    ]
    with factory() as session:
        stored_job = session.get(AIJob, uuid.UUID(job["id"]))
        assert len(stored_job.input_hash) == 64 and stored_job.usage["total_tokens"] == 180
        assert session.scalar(select(func.count()).select_from(StorySource)) == 3


def test_manual_ai_errors_and_evidence_permissions(ai, monkeypatch):
    client, factory, _ = ai
    draft = client.post("/api/v1/stories", json={"title": "Manual"}).json()
    path = f"/api/v1/stories/{draft['id']}"
    request = {"base_version": 1, "language": "bn"}
    assert client.post(path + "/ai-draft", json=request).status_code == 422
    request["reporting_notes"] = "Reporter observed the river."
    assert client.post(path + "/ai-draft", json=request).status_code == 422
    request["notes_permitted"] = True
    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    assert client.post(path + "/ai-draft", json=request).status_code == 503
    monkeypatch.setattr(get_settings(), "openai_api_key", "test-not-a-real-key")

    def failed(*_):
        raise GenerationError("OpenAI timed out")

    monkeypatch.setattr(tasks, "generate", failed)
    job_id = client.post(path + "/ai-draft", json=request).json()["job_id"]
    job = client.get(f"/api/v1/ai/jobs/{job_id}").json()
    assert job["status"] == "FAILED" and "timed out" in job["message"]
    assert client.get(path).json()["version"] == 1
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(StoryVersion)) == 1


def test_stale_jobs_quota_and_foreign_preview(ai, monkeypatch):
    client, factory, _ = ai
    monkeypatch.setattr(routes, "enqueue", lambda _: True)
    draft = client.post("/api/v1/stories", json={"title": "Manual"}).json()
    other = client.post("/api/v1/stories", json={"title": "Other"}).json()
    path = f"/api/v1/stories/{draft['id']}"
    request = {
        "base_version": 1,
        "language": "bn",
        "reporting_notes": "River observation",
        "notes_permitted": True,
    }
    job_id = client.post(path + "/ai-draft", json=request).json()["job_id"]
    assert client.post(path + "/ai-draft", json=request).status_code == 409
    with factory() as session:
        job = session.get(AIJob, uuid.UUID(job_id))
        job.created_at = now() - timedelta(minutes=6)
        session.commit()
    assert client.get(f"/api/v1/ai/jobs/{job_id}").json()["status"] == "FAILED"
    monkeypatch.setattr(tasks, "generate", lambda *_: (generated(), {}))
    monkeypatch.setattr(
        routes, "enqueue", lambda job_id: bool(tasks.run_job(job_id, factory) or True)
    )
    good = client.post(path + "/ai-draft", json=request).json()["job_id"]
    assert (
        client.patch(
            f"/api/v1/stories/{other['id']}", json=save_payload(other, ai_job_id=good)
        ).status_code
        == 422
    )
    saved = client.patch(path, json=save_payload(draft, body="Human writing")).json()
    assert client.patch(path, json=save_payload(saved, ai_job_id=good)).status_code == 409
    assert client.post(path + "/ai-draft", json=request).status_code == 409
    monkeypatch.setattr(get_settings(), "ai_hourly_limit", 2)
    request["base_version"] = 2
    assert client.post(path + "/ai-draft", json=request).status_code == 429


def test_prohibited_source_not_sent_to_ai(ai, monkeypatch):
    client, _, _ = ai
    source = add_source(client)
    collect(client, source)
    item = client.get("/api/v1/feeds/items").json()["items"][0]
    draft = client.post(f"/api/v1/feeds/items/{item['id']}/draft").json()
    client.patch(f"/api/v1/sources/{source['id']}", json={"rights": "prohibited"})
    monkeypatch.setattr(tasks, "generate", lambda *_: pytest.fail("Must not call provider"))
    response = client.post(
        f"/api/v1/stories/{draft['id']}/ai-draft", json={"base_version": 1, "language": "en"}
    )
    assert response.status_code == 422 and "permitted evidence" in response.text


def test_new_endpoints_require_editor_and_reject_invalid_fields(ai):
    client, _, _ = ai
    draft = client.post("/api/v1/stories", json={"title": "Manual"}).json()
    assert client.post("/api/v1/stories", json={"title": " "}).status_code == 422
    assert (
        client.patch(
            f"/api/v1/stories/{draft['id']}",
            json=save_payload(draft, social_captions={"wordpress": "x"}),
        ).status_code
        == 422
    )
    for method, path, body in [
        ("GET", "/api/v1/stories", None),
        ("POST", "/api/v1/stories", {"title": "x"}),
        ("GET", f"/api/v1/stories/{draft['id']}/versions", None),
        ("GET", f"/api/v1/stories/{draft['id']}/ai-jobs", None),
        ("GET", f"/api/v1/ai/jobs/{uuid.uuid4()}", None),
        ("POST", f"/api/v1/stories/{draft['id']}/ai-draft", {"base_version": 1, "language": "bn"}),
    ]:
        assert (
            client.request(method, path, json=body, headers={"Authorization": ""}).status_code
            == 401
        )
