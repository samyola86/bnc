"""Offline visual evidence; the supplied reference is never a runtime asset.

Run inside the API container with the handoff PNG and a read-only exported story JSON.
"""

import argparse
import io
import json
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw

from app.newsbite.newspaper import GRID, paper
from app.newsbite.renderer import render
from app.newsbite.schema import NewsBite
from app.newsbite.service import render_content


def generate(reference_path, story_path, output):
    output.mkdir(parents=True, exist_ok=True)
    reference = Image.open(reference_path).convert("RGB")
    scaled = reference.resize((1080, 1080), Image.Resampling.LANCZOS)
    # Only for this evidence sample: extract the supplied reference photograph.
    # This photograph is never bundled or loaded by the runtime renderer.
    photo = reference.crop((61, 895, 1193, 1206))
    c = NewsBite(
        template_version=2,
        layout_version=2,
        headline="HEADLINE GOES HERE\nSECOND LINE OF\nMAIN STORY",
        footer="",
        publication_date=date(2026, 10, 24),
    )
    png, result = render(c, photo)
    assert not result["errors"], result["errors"]
    (output / "placeholder.png").write_bytes(png)
    image = Image.open(io.BytesIO(png))
    header = Image.new("RGB", (1080, 710), "white")
    header.paste(scaled.crop((0, 0, 1080, 345)), (0, 20))
    header.paste(image.crop((0, 0, 1080, 345)), (0, 365))
    d = ImageDraw.Draw(header)
    d.text((10, 3), "Approved reference, normalized to 1080px", fill="black")
    d.text(
        (10, 348), "Newspaper v2: approximated fonts; real saved date; BNCNEWS.NET", fill="black"
    )
    header.save(output / "header-comparison.png")
    Image.blend(scaled.crop((0, 0, 1080, 345)), image.crop((0, 0, 1080, 345)), 0.5).save(
        output / "header-overlay.png"
    )
    separator = result["layout"]["separator_y"]
    crop = Image.new("RGB", (1080, 200), "white")
    crop.paste(scaled.crop((0, 730, 1080, 830)), (0, 0))
    crop.paste(image.crop((0, separator - 22, 1080, separator + 78)), (0, 100))
    crop.save(output / "photo-edge-comparison.png")
    data = json.loads(Path(story_path).read_text())
    original = dict(data["news_bite"])
    data["news_bite"] = {
        **original,
        "template_id": "newspaper",
        "template_version": 1,
        "layout_version": 1,
    }
    old, _ = render_content(data)
    (output / "mahbubani-v1.png").write_bytes(old)
    data["news_bite"].update(template_version=2, layout_version=2)
    new, story_result = render_content(data)
    assert not story_result["errors"], story_result["errors"]
    (output / "mahbubani-v2.png").write_bytes(new)
    pair = Image.new("RGB", (1080, 705), "white")
    for x, blob, label in [
        (0, old, "Saved content / legacy v1"),
        (540, new, "Same content and focal point / v2"),
    ]:
        pair.paste(Image.open(io.BytesIO(blob)).resize((540, 675)), (x, 30))
        ImageDraw.Draw(pair).text((x + 10, 8), label, fill="black")
    pair.save(output / "before-after.png")
    for language, headline in [
        ("en-short", "Trusted reporting for Bangladesh today"),
        (
            "en-long",
            "Bangladesh communities are working together to strengthen trusted reporting, "
            "protect public interests and ensure that every citizen can access clear information "
            "about the decisions shaping our shared future and daily lives.",
        ),
        ("bn-short", "বাংলাদেশের মানুষের জন্য নির্ভরযোগ্য সংবাদ"),
        (
            "bn-long",
            "বাংলাদেশের মানুষের জন্য নির্ভরযোগ্য সংবাদ এবং সঠিক তথ্য পৌঁছে দিতে আমরা কাজ করছি। "
            "প্রতিটি মানুষের অধিকার ও প্রতিটি অঞ্চলের কথা তুলে ধরতে প্রয়োজন স্বাধীন সাংবাদিকতা, "
            "দায়িত্বশীল প্রতিবেদন এবং সব তথ্য যাচাই করার অঙ্গীকার।",
        ),
    ]:
        for emphasis in [False, True]:
            sample = c.model_copy(
                update={"headline": headline, "highlight": headline.split()[0] if emphasis else ""}
            )
            blob, info = render(sample, photo)
            assert not info["errors"], (language, info["errors"])
            (output / f"{language}-{'blue' if emphasis else 'black'}.png").write_bytes(blob)
    report = {
        "reference_size": reference.size,
        "horizontal_scale": 1080 / reference.width,
        "grid": GRID,
        "rendered_header_bounds": result["header_bounds"],
        "reference_bounds_normalized": {
            "masthead": [75, 66, 1015, 199],
            "corporation": [155, 219, 925, 242],
            "date_left": 51,
            "website_right": 1029,
            "rules_y": [39, 261, 308, 320],
            "photo_separator_y": 751,
            "photo_top_y": 768,
        },
        "placeholder_separator_y": separator,
        "paper_rgb_center": paper().getpixel((540, 600)),
        "story_publication_date": original["publication_date"],
        "story_focal_point": [original["focal_x"], original["focal_y"]],
        "fonts": {
            "masthead": "DM Serif Display + 2px ink spread",
            "headline": "Anton",
            "metadata": "Libre Baskerville Bold",
            "bengali": "Noto Sans/Serif Bengali via Raqm",
        },
        "font_identity": "Licensed approximations; original fonts unverified",
    }
    (output / "measurements.json").write_text(json.dumps(report, indent=2))
    # Gallery image uses a normal story-style sample, not the reference screenshot.
    Image.open(io.BytesIO(png)).resize((216, 270), Image.Resampling.LANCZOS).save(
        output / "thumbnail.png"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("reference")
    parser.add_argument("story")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    generate(args.reference, args.story, args.output)
