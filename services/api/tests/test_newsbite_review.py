"""Focused regressions for the News Bite stability review."""

import base64
import hashlib
import io
import random
import uuid
from datetime import date

import pytest
from fastapi import Response
from PIL import Image, features
from pydantic import ValidationError

from app.newsbite import routes, service
from app.newsbite.schema import NewsBite
from tests.test_ingestion import newsroom  # noqa: F401
from tests.test_newsbite import bucket  # noqa: F401


@pytest.mark.parametrize("highlight", ["", "\u0995\u09cd\u09b7"])
def test_complete_bengali_highlight_is_accepted(highlight):
    assert NewsBite(headline="\u0995\u09cd\u09b7", highlight=highlight).highlight == highlight


def test_highlight_cannot_end_inside_bengali_conjunct():
    with pytest.raises(ValidationError):
        NewsBite(headline="\u0995\u09cd\u09b7", highlight="\u0995\u09cd")


@pytest.mark.parametrize(
    "values",
    [
        {"headline": None},
        {"headline": "x" * 1501},
        {"focal_x": float("nan")},
        {"publication_date": "2026-02-30"},
        {"template_version": 2, "layout_version": 1},
    ],
)
def test_malformed_graphic_configuration_is_rejected(values):
    with pytest.raises(ValidationError):
        NewsBite(**values)


@pytest.mark.parametrize("stored", ["valid", "wrong-hash", "undecodable"])
def test_saved_graphic_integrity_returns_validation_errors(monkeypatch, stored):
    output = io.BytesIO()
    Image.new("RGB", (1080, 1350), "navy").save(output, "PNG")
    data = b"damaged PNG" if stored == "undecodable" else output.getvalue()
    config = NewsBite(
        headline="Verified reporting", publication_date=date(2026, 10, 22), image_rights="owned"
    )
    content = {
        "news_bite": config.model_dump(mode="json"),
        "cover_image_id": str(uuid.uuid4()),
        "destinations": [],
    }
    content["news_bite_render"] = {
        "asset_id": str(uuid.uuid4()),
        "version_id": "revision",
        "fingerprint": service.fingerprint(content),
        "width": 1080,
        "height": 1350,
        "sha256": "wrong" if stored == "wrong-hash" else hashlib.sha256(data).hexdigest(),
    }
    # Isolate integrity validation from the host's native font installation.
    monkeypatch.setattr(service, "render_layout_only", lambda *_: ({}, []))
    monkeypatch.setattr(service, "image", lambda _: Response(data, media_type="image/png"))
    errors = service.graphic_errors(content, "revision", verify_storage=True)
    assert bool(errors.get("news_bite_render")) == (stored != "valid")


def test_preview_flags_a_png_that_cannot_be_saved(newsroom, monkeypatch):  # noqa: F811
    client, _, _ = newsroom
    output = io.BytesIO()
    Image.frombytes(
        "RGB", (1080, 1350), random.Random(7).randbytes(1080 * 1350 * 3)
    ).save(output, "PNG")
    assert len(output.getvalue()) > service.MAX_BYTES
    result = {"errors": [], "warnings": [], "width": 1080, "height": 1350}
    # Exercise the same size boundary independently of native font availability.
    def rendered(_):
        return output.getvalue(), result

    monkeypatch.setattr(service, "render_content", rendered)
    monkeypatch.setattr(routes, "render_content", rendered)
    config = NewsBite(
        headline="Trusted reporting", publication_date=date(2026, 10, 22)
    ).model_dump(mode="json")
    draft = client.post("/api/v1/stories", json={"title": "Boundary check"}).json()
    payload = {"news_bite": config, "cover_image_id": str(uuid.uuid4())}
    preview = client.post(f"/api/v1/stories/{draft['id']}/news-bite/preview", json=payload)
    assert preview.status_code == 200, preview.text
    saved = client.post(
        "/api/v1/stories", json={"title": "Boundary check", "format": "news_bite", **payload}
    )
    assert saved.status_code == 422, saved.text
    assert preview.json()["errors"], "Preview must identify a graphic that saving will reject"


@pytest.mark.skipif(not features.check("raqm"), reason="Requires production Raqm shaping")
def test_permitted_detailed_photo_can_preview_and_save(newsroom, bucket):  # noqa: F811
    client, _, _ = newsroom
    photo = Image.frombytes("RGB", (1080, 1350), random.Random(7).randbytes(1080 * 1350 * 3))
    encoded = io.BytesIO()
    photo.save(encoded, "JPEG", quality=80, subsampling=0)
    assert len(encoded.getvalue()) < 3 * 1024 * 1024
    upload = client.post(
        "/api/v1/media", json={"data": base64.b64encode(encoded.getvalue()).decode()}
    )
    assert upload.status_code == 201, upload.text
    draft = client.post("/api/v1/stories", json={"title": "Detailed photograph"}).json()
    config = NewsBite(
        template_id="dark-editorial", template_version=2, layout_version=2,
        headline="Trusted original reporting", publication_date=date(2026, 10, 22),
        image_rights="owned",
    ).model_dump(mode="json")
    payload = {"news_bite": config, "cover_image_id": upload.json()["id"]}
    preview = client.post(f"/api/v1/stories/{draft['id']}/news-bite/preview", json=payload)
    assert preview.status_code == 200, preview.text
    saved = client.post(
        "/api/v1/stories", json={"title": "Detailed photograph", "format": "news_bite", **payload}
    )
    if len(base64.b64decode(preview.json()["png"])) > service.MAX_BYTES:
        assert preview.json()["errors"]
        assert saved.status_code == 422, saved.text
    else:
        assert not preview.json()["errors"]
        assert saved.status_code == 201, saved.text
