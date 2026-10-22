import io
from datetime import date

import pytest
from PIL import Image, ImageDraw

from app.newsbite.renderer import definitions, layout, render
from app.newsbite.schema import NewsBite


@pytest.mark.parametrize("template", ["dark-editorial", "breaking-news"])
@pytest.mark.parametrize("count", [5, 15, 30, 50])
@pytest.mark.parametrize("language", ["en", "bn"])
def test_reference_layout_preserves_text_and_photo_safe_zone(template, count, language):
    words = (
        "Trusted reporting for Bangladesh and its citizens"
        if language == "en"
        else "বাংলাদেশের মানুষের জন্য নির্ভরযোগ্য সংবাদ এবং সঠিক তথ্য"
    )
    headline = " ".join((words.split() * 12)[:count])
    highlight = "Bangladesh" if language == "en" else "নির্ভরযোগ্য সংবাদ"
    config = NewsBite(
        template_id=template,
        template_version=2,
        layout_version=2,
        headline=headline,
        highlight=highlight if highlight in headline else "",
        publication_date=date.today(),
    )
    scene, errors = layout(config)
    assert scene or errors
    if scene:
        assert scene["head_y"] >= 480
        assert scene["image_height"] >= 300
        assert " ".join(text for text, _ in scene["headline"]["lines"]) == headline
        assert scene["photo_frame"][3] == 1350
        assert scene["photo_frame"][1] == 0
        used = sum(
            scene[key]["height"] + 24
            for key in ["headline", "supporting", "attribution", "credits"]
            if scene[key]["height"]
        )
        assert scene["head_y"] + used <= 1220
    if count <= 15:
        assert not errors


@pytest.mark.parametrize("template", ["dark-editorial", "breaking-news"])
def test_full_background_fade_and_legacy_versions(template):
    photo = Image.new("RGB", (1200, 1600), "#a0d7ef")
    ImageDraw.Draw(photo).rectangle((300, 300, 900, 950), fill="#3a8765")
    config = NewsBite(
        template_id=template,
        template_version=2,
        layout_version=2,
        headline=(
            "Our only identity is not our religion; "
            "our only identity is that we are citizens of Bangladesh."
        ),
        highlight="our only identity is that we are citizens of Bangladesh.",
        supporting="Whatever religion we belong to, religion is our personal matter.",
        speaker="PM TARIQUE RAHMAN",
        publication_date=date(2026, 10, 21),
        footer="READ MORE",
    )
    data, result = render(config, photo)
    assert not result["errors"]
    image = Image.open(io.BytesIO(data))
    assert image.size == (1080, 1350)
    # The photo is visible beyond the former framed-image region, and the
    # decorative red shapes must not punch holes through the lower fade.
    assert max(image.getpixel((500, 1340))) < 80
    assert image.getpixel((600, 300)) != (16, 24, 39)
    if template == "breaking-news":
        red, green, blue = image.getpixel((250, 400))
        assert red > 70 and green < 20 and blue < 30
    assert data == render(config, photo)[0]
    old = config.model_copy(update={"template_version": 1, "layout_version": 1})
    assert render(old, photo)[0] != data
    assert render(old, photo)[0] == render(old, photo)[0]
    start = config.headline.index(config.highlight)
    assert result["layout"]["headline"]["lines"][2][1] == start or any(
        offset == start for _, offset in result["layout"]["headline"]["lines"]
    )


def test_matching_versions_and_current_template_catalog():
    with pytest.raises(ValueError):
        NewsBite(template_version=2, layout_version=1)
    with pytest.raises(ValueError):
        NewsBite(template_id="newspaper", template_version=2, layout_version=2)
    items = {item["id"]: item for item in definitions()}
    assert items["dark-editorial"]["version"] == 2
    assert items["breaking-news"]["full_bleed"]
    assert items["newspaper"]["version"] == 1
