import base64
import hashlib
import io
import uuid
from datetime import date

import pytest
from PIL import Image, ImageDraw
from sqlalchemy import select

from app.auth.models import User
from app.media import routes as media
from app.newsbite import service
from app.newsbite.renderer import TEMPLATES, layout, render
from app.newsbite.schema import NewsBite
from tests.test_ai_stories import save_payload
from tests.test_ingestion import newsroom  # noqa: F401


@pytest.mark.parametrize("template", TEMPLATES)
@pytest.mark.parametrize("count", [5, 15, 30, 50])
@pytest.mark.parametrize("language", ["en", "bn"])
def test_adaptive_geometry_and_unicode(template, count, language):
    words = (
        "Bangladesh citizens deserve trusted original reporting today"
        if language == "en"
        else "বাংলাদেশের মানুষ নির্ভরযোগ্য সংবাদ এবং সুন্দর ভবিষ্যৎ প্রত্যাশা করেন"
    )
    headline = " ".join((words.split() * 10)[:count])
    config = NewsBite(template_id=template, headline=headline, publication_date=date(2026, 10, 22))
    scene, errors = layout(config, "News")
    assert scene or errors
    if scene:
        t = TEMPLATES[template]
        assert t.headline_min <= scene["headline"]["size"] <= t.headline_preferred
        assert t.image_min <= scene["image_height"] <= t.image_max
        assert " ".join(line for line, _ in scene["headline"]["lines"]) == headline
        used = (
            scene["headline_height"]
            + scene["supporting"]["height"]
            + scene["credits"]["height"]
            + scene["image_height"]
            + scene["category"]["height"]
            + 4 * t.gap
        )
        if template == "modern-magazine":
            assert scene["photo_frame"] == (0, 0, 1080, 1350)
            assert scene["positions"]["footer"] + scene["footer"]["height"] <= 1028
        else:
            assert used <= t.bottom - t.top
    if count <= 15:
        assert not errors


def test_excessive_text_explicitly_blocks_without_clipping():
    for template in TEMPLATES:
        _, errors = layout(
            NewsBite(template_id=template, headline="বাংলাদেশ " * 150, publication_date=date.today())
        )
        assert any("does not fit" in error for error in errors)
    with pytest.raises(ValueError):
        NewsBite(headline="Headline", highlight="not present")
    with pytest.raises(ValueError):
        NewsBite(focal_x=1.1)
    with pytest.raises(ValueError):
        NewsBite(headline="বাংলাদেশ", highlight="ব")


def test_readiness_rejects_foreign_revision_artifact_rights_and_missing_captions():
    content = {
        "news_bite": NewsBite(
            headline="Original reporting", publication_date=date.today()
        ).model_dump(mode="json"),
        "cover_image_id": str(uuid.uuid4()),
        "destinations": ["instagram"],
    }
    content["news_bite_render"] = {
        "asset_id": str(uuid.uuid4()),
        "version_id": "other",
        "fingerprint": service.fingerprint(content),
        "width": 1080,
        "height": 1350,
    }
    errors = service.graphic_errors(content, "current")
    assert {"news_bite_render", "news_bite_rights", "social_captions"} <= errors.keys()
    content["news_bite"]["image_rights"] = "licensed"
    content["social_captions"] = {"instagram": "A caption with #BNC and supporting links"}
    content["news_bite_render"].update(
        version_id="current", fingerprint=service.fingerprint(content)
    )
    assert not service.graphic_errors(content, "current")


@pytest.mark.parametrize("dimensions", [(1600, 900), (900, 1600), (1100, 1100), (120, 90)])
def test_crop_export_dimensions_determinism_and_original_preservation(dimensions):
    photo = Image.new("RGB", dimensions, "#dd8855")
    ImageDraw.Draw(photo).rectangle((0, 0, dimensions[0] // 3, dimensions[1]), fill="blue")
    ImageDraw.Draw(photo).rectangle((0, 0, dimensions[0], dimensions[1] // 4), fill="green")
    original = photo.tobytes()
    for template in TEMPLATES:
        config = NewsBite(
            template_id=template,
            headline="Citizens deserve original trusted reporting",
            highlight="original trusted",
            publication_date=date.today(),
        )
        png, result = render(config, photo, "NEWS")
        assert not result["errors"]
        assert Image.open(io.BytesIO(png)).size == (1080, 1350)
        assert png == render(config, photo, "NEWS")[0]
        t = TEMPLATES[template]
        assert bool(result["warnings"]) == (
            dimensions[0] < (1080 if template == "modern-magazine" else t.width)
            or dimensions[1] < result["layout"]["image_height"]
        )
        moved, _ = render(config.model_copy(update={"focal_x": 0, "focal_y": 0}), photo, "NEWS")
        assert png != moved
    assert photo.tobytes() == original


@pytest.fixture
def bucket(monkeypatch):
    class Bucket:
        def __init__(self):
            self.items = {}

        def put_object(self, **kwargs):
            self.items[kwargs["Key"]] = kwargs

        def get_object(self, **kwargs):
            value = self.items[kwargs["Key"]]
            return {"Body": io.BytesIO(value["Body"]), "ContentType": value["ContentType"]}

    value = Bucket()
    monkeypatch.setattr(media, "storage", lambda: value)
    monkeypatch.setattr(service, "storage", lambda: value)
    return value


@pytest.mark.parametrize(
    "template,version",
    [
        ("newspaper", 1),
        ("newspaper", 2),
        ("modern-magazine", 1),
        ("dark-editorial", 2),
        ("breaking-news", 2),
    ],
)
def test_preview_persistence_revision_approval_and_byte_parity(newsroom, bucket, template, version):  # noqa: F811
    client, factory, _ = newsroom
    photo = io.BytesIO()
    Image.new("RGB", (1300, 1300), "navy").save(photo, "PNG")
    asset = client.post(
        "/api/v1/media", json={"data": base64.b64encode(photo.getvalue()).decode()}
    ).json()["id"]
    config = NewsBite(
        template_id=template,
        template_version=version,
        layout_version=version,
        headline="Original reporting for a stronger Bangladesh",
        highlight="stronger Bangladesh",
        publication_date=date.today(),
        image_rights="owned",
    ).model_dump(mode="json")
    payload = {
        "title": "Story record",
        "format": "news_bite",
        "news_bite": config,
        "cover_image_id": asset,
        "category": "Bangladesh",
        "tags": ["News"],
        "contributors": ["Reporter"],
        "destinations": ["facebook", "instagram"],
        "social_captions": {"facebook": "FB caption", "instagram": "IG caption"},
    }
    response = client.post("/api/v1/stories", json=payload)
    assert response.status_code == 201, response.text
    draft = response.json()
    path = f"/api/v1/stories/{draft['id']}"
    preview = client.post(
        path + "/news-bite/preview",
        json={"news_bite": config, "cover_image_id": asset, "category": "Bangladesh"},
    ).json()
    artifact = draft["news_bite_render"]
    saved_png = client.get("/api/v1/media/" + artifact["asset_id"]).content
    assert saved_png == base64.b64decode(preview["png"])
    assert hashlib.sha256(saved_png).hexdigest() == artifact["sha256"]
    assert artifact["version_id"] == draft["version_id"]
    assert client.get(path).json()["news_bite"] == config
    submitted = client.post(path + "/submit-review", json={"base_version": 1})
    assert submitted.status_code == 201, submitted.text
    request_id = submitted.json()["id"]
    decision = {
        "base_version": 1,
        "request_id": request_id,
        "self_approval_override": True,
        "notes": "Test administrative override",
    }
    assert client.post(path + "/approve", json=decision).status_code == 200
    assert client.post(path + "/ready", json=decision).status_code == 200
    updated = client.patch(
        path,
        json=save_payload(
            draft,
            news_bite={**config, "focal_x": 0.1},
            social_captions={"facebook": "Changed caption"},
        ),
    ).json()
    assert updated["status"] == "DRAFT" and updated["version"] == 2
    assert updated["news_bite_render"]["version_id"] != artifact["version_id"]
    assert (
        client.get("/api/v1/publishing/requests/" + request_id).json()["request"]["status"]
        == "CANCELLED"
    )
    assert client.get(path + "/versions").json()["items"][1]["content"]["news_bite"] == config
    # Clients cannot forge a render record or supply a different story's preview authorization.
    assert (
        client.patch(path, json=save_payload(updated, news_bite_render=artifact)).status_code == 422
    )
    with factory() as session:
        actor = session.scalar(select(User))
        actor.role = "CONTENT_WRITER"
        session.commit()
    assert client.post(path + "/approve", json=decision).status_code == 403
    other = client.post("/api/v1/stories", json={"title": "Other"}).json()
    with factory() as session:
        from app.editorial.models import Story

        foreign = User(name="Other", username="other", email="other@example.test", role="EDITOR")
        session.add(foreign)
        session.flush()
        session.get(Story, uuid.UUID(other["id"])).author_id = foreign.id
        session.commit()
    assert (
        client.post(
            f"/api/v1/stories/{other['id']}/news-bite/preview", json={"news_bite": config}
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "change",
    [
        {"news_bite": None},
        {"cover_image_id": None},
        {"news_bite": {"headline": "Too long " * 150, "publication_date": "2026-10-22"}},
        {
            "news_bite": {
                "headline": "Report",
                "publication_date": "2026-10-22",
                "image_rights": "prohibited",
            }
        },
    ],
)
def test_incomplete_news_bites_save_but_cannot_submit(newsroom, bucket, change):  # noqa: F811
    client, _, _ = newsroom
    result = client.post(
        "/api/v1/stories", json={"title": "Incomplete", "format": "news_bite", **change}
    )
    assert result.status_code == 201, result.text
    assert (
        client.post(
            f"/api/v1/stories/{result.json()['id']}/submit-review", json={"base_version": 1}
        ).status_code
        == 422
    )
