import io
from datetime import date

import pytest
from PIL import Image, ImageDraw, ImageOps

from app.newsbite.magazine import PANEL, TEXT_BOTTOM, TEXT_WIDTH, TEXT_X
from app.newsbite.renderer import layout, render
from app.newsbite.schema import NewsBite


def config(**values):
    return NewsBite(template_id="modern-magazine", publication_date=date(2026, 10, 24), **values)


@pytest.mark.parametrize("language", ["en", "bn"])
@pytest.mark.parametrize("count", [5, 15, 30, 50])
def test_glass_panel_fits_or_reports_overflow(language, count):
    words = (
        "Trusted reporting for Bangladesh citizens and communities"
        if language == "en"
        else "বাংলাদেশের মানুষের জন্য নির্ভরযোগ্য সংবাদ এবং সঠিক তথ্য"
    )
    headline = " ".join((words.split() * 10)[:count])
    scene, errors = layout(
        config(headline=headline, supporting="Clear original reporting."), "Politics"
    )
    assert scene or errors
    if scene:
        assert scene["panel"] == PANEL
        assert scene["photo_frame"] == (0, 0, 1080, 1350)
        assert " ".join(line for line, _ in scene["headline"]["lines"]) == headline
        assert scene["positions"]["footer"] + scene["footer"]["height"] <= TEXT_BOTTOM
        assert scene["category"]["lines"] == [("POLITICS", 0)]
    if count <= 15:
        assert not errors


def test_category_orange_is_independent_of_headline_highlight():
    c = config(
        headline="Bangladesh news today", highlight="Bangladesh", supporting="A clear summary."
    )
    photo = Image.new("RGB", (1200, 1600), "#465365")
    data, result = render(c, photo, "Economy")
    assert not result["errors"]
    image = Image.open(io.BytesIO(data))
    scene = result["layout"]
    y = scene["positions"]["category"]
    area = (TEXT_X, y, TEXT_X + TEXT_WIDTH, y + scene["category"]["height"])
    pixels = image.crop(area).tobytes()
    assert any(pixels[i : i + 3] == bytes((255, 121, 28)) for i in range(0, len(pixels), 3))
    plain = Image.open(
        io.BytesIO(render(c.model_copy(update={"highlight": ""}), photo, "Economy")[0])
    )
    assert plain.crop(area).tobytes() == image.crop(area).tobytes()
    hy = scene["positions"]["headline"]
    head = (TEXT_X, hy, TEXT_X + TEXT_WIDTH, hy + scene["headline"]["height"])
    assert plain.crop(head).tobytes() != image.crop(head).tobytes()


def test_full_photo_focal_crop_and_original_preserved():
    photo = Image.new("RGB", (1600, 1000), "#a8b8c8")
    ImageDraw.Draw(photo).rectangle((0, 0, 500, 1000), fill="red")
    original = photo.tobytes()
    c = config(
        headline="HEADLINE GOES HERE",
        supporting="Add the news summary here.",
        footer="",
        focal_x=0.1,
        focal_y=0.8,
    )
    data, result = render(c, photo, "World")
    image = Image.open(io.BytesIO(data))
    expected = ImageOps.fit(photo, (1080, 1350), Image.Resampling.LANCZOS, centering=(0.1, 0.8))
    assert image.getpixel((900, 500)) == expected.getpixel((900, 500))
    assert image.getpixel((200, 500)) != expected.getpixel((200, 500))
    assert photo.tobytes() == original
    assert image.size == (1080, 1350) and not result["errors"]
    assert data == render(c, photo, "World")[0]


def test_missing_category_and_impossible_copy_are_explicit():
    _, errors = layout(config(headline="Headline"), "")
    assert any("news category" in error for error in errors)
    _, errors = layout(config(headline="Bangladesh " * 120), "World")
    assert any("does not fit" in error for error in errors)
