import io
from datetime import date

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageOps

from app.newsbite.newspaper import GRID, paper
from app.newsbite.renderer import layout, render
from app.newsbite.schema import NewsBite


def config(**values):
    return NewsBite(
        template_id="newspaper",
        template_version=2,
        layout_version=2,
        publication_date=date(2026, 10, 22),
        **values,
    )


@pytest.mark.parametrize("language", ["en", "bn"])
@pytest.mark.parametrize("count", [5, 15, 30, 50])
@pytest.mark.parametrize("emphasis", [False, True])
def test_adaptive_newspaper_text_and_optional_fields(language, count, emphasis):
    words = (
        "Bangladesh citizens deserve trusted original reporting today"
        if language == "en"
        else "বাংলাদেশের মানুষ নির্ভরযোগ্য সংবাদ এবং সুন্দর ভবিষ্যৎ প্রত্যাশা করেন"
    )
    headline = " ".join((words.split() * 10)[:count])
    c = config(
        headline=headline,
        highlight=words.split()[0] if emphasis else "",
        supporting="Verified original reporting.",
        speaker="BNC reporter",
        source_credit="BNC reporting",
        footer="Trusted News. A Stronger Bangladesh.",
    )
    scene, errors = layout(c, "NEWS", "Photo credit")
    assert not errors
    assert " ".join(line for line, _ in scene["headline"]["lines"]) == headline
    assert GRID["headline_min"] <= scene["headline"]["size"] <= GRID["headline_preferred"]
    assert scene["image_height"] >= GRID["image_min"]
    assert scene["footer_y"] + scene["footer"]["height"] <= GRID["bottom"]


def test_visible_header_grid_saved_date_and_rules():
    data, result = render(config(headline="HEADLINE GOES HERE", footer=""))
    image = Image.open(io.BytesIO(data))
    assert image.size == (1080, 1350)
    bounds = result["header_bounds"]
    assert bounds["website"][2] == GRID["right"] + 1
    painted = ImageChops.difference(
        image.crop((750, 270, 1050, 305)), paper().crop((750, 270, 1050, 305))
    ).getbbox()
    assert painted[2] + 750 == GRID["right"] + 1
    assert bounds["date"][0] == GRID["x"]
    assert bounds["masthead"][0] + bounds["masthead"][2] == 2 * GRID["masthead_center"]
    for y in (
        GRID["top_rule"],
        GRID["corporation_rule"],
        GRID["metadata_rule"],
        GRID["double_rule"],
    ):
        assert image.getpixel((GRID["x"], y)) == (16, 16, 14)
        assert image.getpixel((GRID["right"], y)) == (16, 16, 14)
    # The date comes from the saved configuration, never a placeholder or wall clock.
    c = config(headline="HEADLINE GOES HERE", footer="")
    changed, _ = render(c.model_copy(update={"publication_date": date(2026, 10, 23)}))
    other = Image.open(io.BytesIO(changed))
    assert image.crop((51, 278, 600, 305)).tobytes() != other.crop((51, 278, 600, 305)).tobytes()


@pytest.mark.parametrize("dimensions", [(1600, 900), (900, 1600), (1100, 1100)])
@pytest.mark.parametrize("focal", [(0, 0), (0.46, 0.46), (1, 1)])
def test_photo_border_separator_and_focal_crop(dimensions, focal):
    photo = Image.new("RGB", dimensions, "#aabbcc")
    ImageDraw.Draw(photo).rectangle((0, 0, dimensions[0] // 3, dimensions[1]), fill="blue")
    original = photo.tobytes()
    c = config(headline="Original reporting", footer="", focal_x=focal[0], focal_y=focal[1])
    data, result = render(c, photo)
    assert not result["errors"]
    image = Image.open(io.BytesIO(data))
    x, y, right, bottom = result["layout"]["photo_frame"]
    expected = ImageOps.fit(
        photo, (right - x, bottom - y), method=Image.Resampling.LANCZOS, centering=focal
    )
    assert (
        image.crop((x + 2, y + 2, right - 2, bottom - 2)).tobytes()
        == expected.crop((2, 2, right - x - 2, bottom - y - 2)).tobytes()
    )
    assert image.getpixel((x, y)) == (16, 16, 14)
    assert image.getpixel((right - 1, bottom - 1)) == (16, 16, 14)
    assert image.getpixel((x, result["layout"]["separator_y"])) == (16, 16, 14)
    assert photo.tobytes() == original
    assert data == render(c, photo)[0]


def test_empty_optional_fields_overflow_emphasis_and_legacy():
    c = config(headline="HEADLINE GOES HERE\nSECOND LINE OF\nMAIN STORY", footer="")
    data, result = render(c)
    scene = result["layout"]
    assert scene["positions"]["headline"] == GRID["story_top"]
    assert scene["supporting"]["height"] == scene["credits"]["height"] == 0
    assert len(scene["headline"]["lines"]) == 3
    assert render(c.model_copy(update={"highlight": "MAIN STORY"}))[0] != data
    legacy = c.model_copy(update={"template_version": 1, "layout_version": 1})
    assert render(legacy)[0] != data
    assert render(legacy)[0] == render(legacy)[0]
    _, errors = layout(config(headline="Bangladesh " * 120))
    assert any("does not fit" in error for error in errors)
    assert paper().getextrema()[0][0] != paper().getextrema()[0][1]
