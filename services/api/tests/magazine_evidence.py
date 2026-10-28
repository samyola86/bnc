"""Render the current Modern Magazine design with an editor-supplied photograph."""

import argparse
import io
from datetime import date
from pathlib import Path

from PIL import Image

from app.newsbite.renderer import render
from app.newsbite.schema import NewsBite


def generate(photo_path, output):
    output.mkdir(parents=True, exist_ok=True)
    config = NewsBite(
        template_id="modern-magazine",
        headline="HEADLINE\nGOES HERE",
        supporting="Add the news\nsummary here.\n\nKeep the key details\nclear and concise.",
        footer="",
        publication_date=date(2026, 10, 24),
    )
    with Image.open(photo_path) as photo:
        for name, cover in [("photo-layout", photo), ("orange-layout", None)]:
            data, result = render(config, cover, "World News")
            assert not result["errors"], result["errors"]
            (output / f"{name}.png").write_bytes(data)
            if cover is not None:
                Image.open(io.BytesIO(data)).resize((216, 270), Image.Resampling.LANCZOS).save(
                    output / "thumbnail.png"
                )
        bengali = config.model_copy(
            update={
                "headline": "বাংলাদেশের মানুষের জন্য নির্ভরযোগ্য সংবাদ",
                "supporting": "সঠিক তথ্য, স্পষ্ট প্রেক্ষাপট এবং মানুষের কথা।",
            }
        )
        data, result = render(bengali, photo, "বাংলাদেশ")
        assert not result["errors"], result["errors"]
        (output / "bengali.png").write_bytes(data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("photo")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    generate(args.photo, args.output)
