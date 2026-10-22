"""Generate reproducible template evidence using a supplied permitted photograph."""

import argparse
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw

from app.newsbite.renderer import TEMPLATES, render
from app.newsbite.schema import NewsBite


def generate(photo_path, output):
    output.mkdir(parents=True, exist_ok=True)
    photo = Image.open(photo_path)
    sheet = Image.new("RGB", (4 * 270, 2 * 370), "#e2e8f0")
    for column, template in enumerate(TEMPLATES):
        for row, headline in enumerate(
            [
                "Trusted reporting for Bangladesh today",
                "Our only identity is not our religion; our only identity is that we are citizens "
                "of Bangladesh, working together to build a stronger future for every community "
                "in our country.",
            ]
        ):
            config = NewsBite(
                template_id=template,
                template_version=2 if template in {"dark-editorial", "breaking-news"} else 1,
                layout_version=2 if template in {"dark-editorial", "breaking-news"} else 1,
                headline=headline,
                highlight="Bangladesh"
                if row == 0
                else "our only identity is that we are citizens of Bangladesh,",
                supporting="Independent reporting. Clear context. Stories that matter.",
                speaker="BNC NEWSROOM",
                source_credit="BNC reporting",
                publication_date=date(2026, 10, 22),
                image_rights="owned",
            )
            png, result = render(
                config, photo, "HOT NEWS", "Photo: BNC supplied newsroom background"
            )
            assert not result["errors"], (template, result["errors"])
            suffix = "short" if row == 0 else "long"
            (output / f"{template}-{suffix}.png").write_bytes(png)
            import io

            thumbnail = Image.open(io.BytesIO(png)).resize((270, 338))
            sheet.paste(thumbnail, (column * 270, row * 370))
            ImageDraw.Draw(sheet).text(
                (column * 270 + 5, row * 370 + 340), f"{template} / {suffix}", fill="black"
            )
    sheet.save(output / "contact-sheet.png")
    bengali = Image.new("RGB", (4 * 270, 2 * 370), "#e2e8f0")
    for column, template in enumerate(TEMPLATES):
        for row, headline in enumerate(
            [
                "বাংলাদেশের মানুষের জন্য নির্ভরযোগ্য সংবাদ",
                "বাংলাদেশের মানুষের জন্য নির্ভরযোগ্য সংবাদ এবং সঠিক তথ্য পৌঁছে দিতে "
                "আমরা কাজ করছি। প্রতিটি মানুষের অধিকার ও প্রতিটি অঞ্চলের কথা "
                "তুলে ধরতে প্রয়োজন স্বাধীন সাংবাদিকতা, দায়িত্বশীল প্রতিবেদন এবং "
                "সব তথ্য যাচাই করার অঙ্গীকার।",
            ]
        ):
            config = NewsBite(
                template_id=template,
                template_version=2 if template in {"dark-editorial", "breaking-news"} else 1,
                layout_version=2 if template in {"dark-editorial", "breaking-news"} else 1,
                headline=headline,
                highlight="নির্ভরযোগ্য সংবাদ",
                supporting="সঠিক তথ্য, স্পষ্ট প্রেক্ষাপট এবং মানুষের কথা।",
                speaker="বিএনসি সংবাদকক্ষ",
                source_credit="নিজস্ব প্রতিবেদন",
                publication_date=date(2026, 10, 22),
                image_rights="owned",
            )
            png, result = render(config, photo, "বাংলাদেশ", "ছবি: বিএনসি সংবাদকক্ষ")
            assert not result["errors"], (template, result["errors"])
            suffix = "short" if row == 0 else "long"
            (output / f"{template}-bn-{suffix}.png").write_bytes(png)
            thumbnail = Image.open(io.BytesIO(png)).resize((270, 338))
            bengali.paste(thumbnail, (column * 270, row * 370))
            ImageDraw.Draw(bengali).text(
                (column * 270 + 5, row * 370 + 340), f"{template} / bn-{suffix}", fill="black"
            )
    bengali.save(output / "contact-sheet-bengali.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("photo")
    parser.add_argument("output")
    args = parser.parse_args()
    generate(args.photo, Path(args.output))
