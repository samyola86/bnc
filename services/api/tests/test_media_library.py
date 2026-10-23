import base64
import io
import uuid
from datetime import UTC, datetime

from botocore.exceptions import ClientError
from PIL import Image

from app.media import routes as media
from tests.test_ingestion import newsroom  # noqa: F401


def test_upload_list_retrieve_and_reuse(newsroom, monkeypatch):  # noqa: F811
    client, _, _ = newsroom

    class Storage:
        def __init__(self):
            self.objects = {}

        def put_object(self, **kwargs):
            self.objects[kwargs["Key"]] = kwargs

        def list_objects_v2(self, **kwargs):
            assert kwargs["Prefix"] == "covers/"
            assert kwargs["MaxKeys"] == 24
            return {"Contents": [
                {"Key": k, "Size": len(v["Body"]), "LastModified": datetime.now(UTC)}
                for k, v in self.objects.items()
            ]}

        def get_object(self, **kwargs):
            value = self.objects[kwargs["Key"]]
            return {"Body": io.BytesIO(value["Body"]), "ContentType": value["ContentType"]}

    storage = Storage()
    monkeypatch.setattr(media, "storage", lambda: storage)
    assert client.get("/api/v1/media").json() == {"items": [], "next_cursor": None}
    data = io.BytesIO()
    Image.new("RGB", (20, 20), "navy").save(data, "PNG")
    uploaded = client.post("/api/v1/media", json={
        "data": base64.b64encode(data.getvalue()).decode()
    })
    assert uploaded.status_code == 201
    asset_id = uploaded.json()["id"]
    listed = client.get("/api/v1/media").json()
    assert listed["items"][0]["id"] == asset_id
    assert client.get(f"/api/v1/media/{asset_id}").content == data.getvalue()
    for title in ["First story", "Reused image"]:
        result = client.post("/api/v1/stories", json={"title": title, "cover_image_id": asset_id})
        assert result.status_code == 201
        assert result.json()["cover_image_id"] == asset_id
    client.cookies.clear()
    assert client.get("/api/v1/media").status_code == 401


def test_library_pagination_and_storage_errors(newsroom, monkeypatch):  # noqa: F811
    client, _, _ = newsroom
    asset_id = str(uuid.uuid4())

    class Storage:
        def list_objects_v2(self, **kwargs):
            if kwargs.get("ContinuationToken") == "bad":
                raise ClientError({"Error": {"Code": "InvalidArgument"}}, "ListObjectsV2")
            if kwargs.get("ContinuationToken") == "outage":
                raise ClientError({"Error": {"Code": "ServiceUnavailable"}}, "ListObjectsV2")
            assert kwargs.get("ContinuationToken") == "next"
            return {"Contents": [
                {"Key": "covers/not-an-image", "Size": 0, "LastModified": datetime.now(UTC)},
                {"Key": f"covers/{asset_id}", "Size": 10, "LastModified": datetime.now(UTC)},
            ], "NextContinuationToken": "last"}

    monkeypatch.setattr(media, "storage", Storage)
    result = client.get("/api/v1/media?cursor=next")
    assert result.status_code == 200
    assert [item["id"] for item in result.json()["items"]] == [asset_id]
    assert result.json()["next_cursor"] == "last"
    assert client.get("/api/v1/media?cursor=bad").status_code == 422
    assert client.get("/api/v1/media?cursor=outage").status_code == 503
