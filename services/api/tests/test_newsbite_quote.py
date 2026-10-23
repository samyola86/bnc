import io
from datetime import date

from PIL import Image, ImageChops

from app.newsbite import photographic
from app.newsbite.renderer import render
from app.newsbite.schema import NewsBite


def test_supplied_quote_composition_and_removed_social_icons(monkeypatch):
    c = NewsBite(
        template_id="dark-editorial",
        template_version=2,
        layout_version=2,
        headline="Original reporting for Bangladesh",
        publication_date=date(2026, 10, 24),
    )
    photo = Image.new("RGB", (1200, 1600), "#808080")
    original = photo.tobytes()
    data, result = render(c, photo)
    assert not result["errors"]
    image = Image.open(io.BytesIO(data))
    bubble = photographic.quote_bubble()
    assert bubble.mode == "RGBA" and bubble.size == (205, 205)
    assert bubble.getchannel("A").getextrema() == (0, 255)
    monkeypatch.setattr(photographic, "quote_bubble", lambda: Image.new("RGBA", (205, 205)))
    base = Image.open(io.BytesIO(render(c, photo)[0]))
    expected = base.copy()
    expected.paste(bubble, (85, 182), bubble)
    assert ImageChops.difference(image, expected).getbbox() is None
    assert ImageChops.difference(image, base).getbbox() is not None
    # Former social icons at the top right now show only the shaded photograph.
    for x, y in [(825, 128), (880, 128), (936, 128), (990, 128)]:
        shade = round((1 - y / 350) * 205)
        pixel = Image.alpha_composite(
            Image.new("RGBA", (1, 1), (128, 128, 128, 255)),
            Image.new("RGBA", (1, 1), (5, 10, 17, shade)),
        )
        assert image.getpixel((x, y)) == pixel.convert("RGB").getpixel((0, 0))
    assert photo.tobytes() == original


def test_breaking_news_does_not_use_quote_asset(monkeypatch):
    def unexpected():
        raise AssertionError("Quote asset must not affect Breaking News")

    monkeypatch.setattr(photographic, "quote_bubble", unexpected)
    _, result = render(
        NewsBite(
            template_id="breaking-news",
            template_version=2,
            layout_version=2,
            headline="Original reporting",
            publication_date=date(2026, 10, 24),
        )
    )
    assert not result["errors"]
