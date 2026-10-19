import uuid

import pytest

from app.ai import tasks
from app.api.v1 import stories as routes
from tests.test_ai_stories import ai, generated, save_payload  # noqa: F401
from tests.test_ingestion import add_source, collect, newsroom  # noqa: F401


def test_queue_outage_is_persistent_and_safe(ai, monkeypatch):  # noqa: F811
    client, factory, _ = ai
    draft = client.post("/api/v1/stories", json={"title": "Manual"}).json()
    monkeypatch.setattr(tasks, "SessionLocal", factory)
    monkeypatch.setattr(routes, "enqueue", tasks.enqueue)

    def unavailable(*args, **kwargs):
        raise ConnectionError("sensitive-broker-details")

    monkeypatch.setattr(tasks.generate_draft, "apply_async", unavailable)
    path = f"/api/v1/stories/{draft['id']}"
    response = client.post(
        path + "/ai-draft",
        json={
            "base_version": 1,
            "language": "bn",
            "reporting_notes": "River observed",
            "notes_permitted": True,
        },
    )
    assert response.status_code == 503 and "sensitive" not in response.text
    job = client.get(path + "/ai-jobs").json()["items"][0]
    assert job["status"] == "FAILED" and "queue unavailable" in job["message"]
    assert client.get(path).json()["version"] == 1


def test_permission_changes_before_worker_and_duplicate_deliveries(ai, monkeypatch):  # noqa: F811
    client, factory, _ = ai
    source = add_source(client)
    collect(client, source)
    item = client.get("/api/v1/feeds/items").json()["items"][0]
    draft = client.post(f"/api/v1/feeds/items/{item['id']}/draft").json()
    monkeypatch.setattr(routes, "enqueue", lambda _: True)
    path = f"/api/v1/stories/{draft['id']}"
    job_id = uuid.UUID(
        client.post(path + "/ai-draft", json={"base_version": 1, "language": "bn"}).json()["job_id"]
    )
    client.patch(f"/api/v1/sources/{source['id']}", json={"extraction_mode": "reference_only"})
    monkeypatch.setattr(tasks, "generate", lambda *_: pytest.fail("Revoked evidence sent"))
    tasks.run_job(job_id, factory)
    job = client.get(f"/api/v1/ai/jobs/{job_id}").json()
    assert job["status"] == "FAILED" and "permissions changed" in job["message"]
    tasks.run_job(job_id, factory)  # A duplicate delivery cannot consume another provider call.
    assert client.get(path).json()["version"] == 1


def test_manual_ai_generation_with_missing_credits_stays_nonblocking(ai, monkeypatch):  # noqa: F811
    client, _, _ = ai
    draft = client.post("/api/v1/stories", json={"title": "Reporter notes"}).json()
    monkeypatch.setattr(tasks, "generate", lambda *_: (generated(), {}))
    path = f"/api/v1/stories/{draft['id']}"
    job_id = client.post(
        path + "/ai-draft",
        json={
            "base_version": 1,
            "language": "bn",
            "reporting_notes": "Reporter observed the river",
            "notes_permitted": True,
        },
    ).json()["job_id"]
    saved = client.patch(
        path, json=save_payload(draft, body="Edited generated writing", ai_job_id=job_id)
    ).json()
    assert saved["warnings"] == ["Missing source credit"]
    assert saved["attribution_blocks_publishing"] is False and saved["status"] == "DRAFT"
    assert saved["human_review_required"] and saved["provenance"] == []
