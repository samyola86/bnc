import base64
import io
import os
from datetime import UTC, datetime, timedelta

import pytest
from PIL import Image

from app.media import routes as media
from tests.test_ai_stories import save_payload
from tests.test_ingestion import newsroom  # noqa: F401


def story(client, **extra):
    response = client.post(
        "/api/v1/stories",
        json={
            "title": "Original report",
            "body": "Independently reported story.",
            "category": "World",
            "tags": ["News"],
            "contributors": ["Sam", "Nadia"],
            "destinations": ["wordpress", "facebook"],
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_details_revision_persistence_and_backward_compatible_saves(newsroom):  # noqa: F811
    client, _, _ = newsroom
    draft = story(
        client,
        format="news_bite",
        reporting_notes="Reporter notebook",
        image_alt="River",
        image_caption="Photo: Sam",
        social_caption="Brief",
    )
    path = f"/api/v1/stories/{draft['id']}"
    saved = client.patch(path, json=save_payload(draft, title="Updated headline")).json()
    for key in (
        "format",
        "contributors",
        "destinations",
        "reporting_notes",
        "image_alt",
        "image_caption",
        "social_caption",
    ):
        assert saved[key] == draft[key]
    assert saved["version"] == 2
    history = client.get(path + "/versions").json()["items"]
    assert history[1]["content"]["format"] == "news_bite"
    assert history[1]["title"] == "Original report"
    assert client.patch(path, json=save_payload(draft)).status_code == 409
    edited = client.patch(
        path, json=save_payload(saved, contributors=["Rafi"], format="article")
    ).json()
    assert edited["contributors"] == ["Rafi"] and edited["format"] == "article"
    assert client.get(path).json()["contributors"] == ["Rafi"]


def test_queue_schedule_idempotency_and_revision_invalidation(newsroom):  # noqa: F811
    client, _, _ = newsroom
    scheduled = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    draft = story(client, scheduled_at=scheduled)
    path = f"/api/v1/stories/{draft['id']}"
    result = client.post(path + "/queue", json={"base_version": 1})
    assert result.status_code == 201 and result.json()["status"] == "IN_REVIEW"
    assert client.post(path + "/queue", json={"base_version": 1}).json() == result.json()
    entry = client.get("/api/v1/publishing/queue").json()["items"][0]
    assert entry["destinations"] == ["wordpress", "facebook"]
    assert datetime.fromisoformat(entry["scheduled_at"]).replace(tzinfo=UTC) == (
        datetime.fromisoformat(scheduled)
    )
    assert "not enabled" in entry["delivery_status"]
    assert client.get("/api/v1/feeds/summary").json()["awaiting_publication"]["count"] == 1
    assert client.patch(path, json=save_payload(draft)).status_code == 409
    assert client.post(f"/api/v1/publishing/queue/{result.json()['id']}/cancel").status_code == 200
    assert (
        client.patch(
            path,
            json=save_payload(draft, body="Updated reporting", category="World", tags=["News"]),
        ).status_code
        == 200
    )
    assert client.get("/api/v1/publishing/queue").json()["items"] == []
    assert client.get("/api/v1/feeds/summary").json()["awaiting_publication"]["count"] == 0
    assert client.post(path + "/queue", json={"base_version": 1}).status_code == 409
    result = client.post(path + "/queue", json={"base_version": 2}).json()
    assert client.post(f"/api/v1/publishing/queue/{result['id']}/cancel").status_code == 200
    assert client.get("/api/v1/publishing/queue").json()["items"] == []


@pytest.mark.parametrize(
    "fields",
    [
        {"body": ""},
        {"category": ""},
        {"tags": []},
        {"contributors": []},
        {"destinations": []},
        {"destinations": ["instagram"]},
        {"scheduled_at": "2020-01-01T00:00:00+06:00"},
    ],
)
def test_queue_validation_preserves_drafts(newsroom, fields):  # noqa: F811
    client, _, _ = newsroom
    draft = story(client, **fields)
    path = f"/api/v1/stories/{draft['id']}"
    assert client.post(path + "/queue", json={"base_version": 1}).status_code == 422
    assert client.get(path).json()["status"] == "DRAFT"
    assert client.get("/api/v1/publishing/queue").json()["items"] == []


def test_queue_missing_credit_is_nonblocking_and_timezone_validation(newsroom):  # noqa: F811
    client, _, _ = newsroom
    draft = story(client)
    assert draft["warnings"] == ["Missing source credit"]
    assert (
        client.post(f"/api/v1/stories/{draft['id']}/queue", json={"base_version": 1}).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/stories",
            json={
                "title": "Invalid timezone",
                "scheduled_at": "2030-01-01T10:00:00",
            },
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/publishing/queue", headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )


class Bucket:
    def __init__(self):
        self.objects = {}

    def put_object(self, **kwargs):
        self.objects[kwargs["Key"]] = kwargs

    def get_object(self, **kwargs):
        obj = self.objects[kwargs["Key"]]
        return {"ContentType": obj["ContentType"], "Body": io.BytesIO(obj["Body"])}


def test_private_image_upload_roundtrip_and_revision_reference(newsroom, monkeypatch):  # noqa: F811
    client, _, _ = newsroom
    bucket = Bucket()
    monkeypatch.setattr(media, "storage", lambda: bucket)
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buffer, format="PNG")
    data = buffer.getvalue()
    upload = client.post("/api/v1/media", json={"data": base64.b64encode(data).decode()})
    assert upload.status_code == 201
    image_id = upload.json()["id"]
    image = client.get(f"/api/v1/media/{image_id}")
    assert image.content == data and image.headers["content-type"] == "image/png"
    assert (
        client.get(
            f"/api/v1/media/{image_id}", headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
    draft = story(
        client, cover_image_id=image_id, image_alt="Red image", destinations=["instagram"]
    )
    path = f"/api/v1/stories/{draft['id']}"
    assert client.get(path).json()["cover_image_id"] == image_id
    assert client.post(path + "/queue", json={"base_version": 1}).status_code == 201
    request_id = client.get("/api/v1/publishing/queue").json()["items"][0]["id"]
    assert client.post(f"/api/v1/publishing/queue/{request_id}/cancel").status_code == 200
    assert (
        client.patch(path, json=save_payload(draft, cover_image_id=None)).json()["cover_image_id"]
        is None
    )
    versions = client.get(path + "/versions").json()["items"]
    assert versions[1]["content"]["cover_image_id"] == image_id
    for bad in (
        "invalid base64",
        base64.b64encode(b"<svg>not an image</svg>").decode(),
        base64.b64encode(data[:-12]).decode(),
    ):
        assert client.post("/api/v1/media", json={"data": bad}).status_code == 422
    assert len(bucket.objects) == 1


@pytest.mark.skipif(not os.environ.get("BNC_TEST_MEDIA"), reason="Opt-in real object-storage check")
def test_real_private_object_storage(newsroom):  # noqa: F811
    client, _, _ = newsroom
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(buffer, format="PNG")
    response = client.post(
        "/api/v1/media",
        json={
            "data": base64.b64encode(buffer.getvalue()).decode(),
        },
    )
    assert response.status_code == 201, response.text
    media_id = response.json()["id"]
    try:
        image = client.get(f"/api/v1/media/{media_id}")
        assert image.status_code == 200 and image.content == buffer.getvalue()
    finally:
        media.storage().delete_object(
            Bucket=media.get_settings().s3_bucket, Key=f"covers/{media_id}"
        )
