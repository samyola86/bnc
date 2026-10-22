"""Reference-text comparison for the corrected full-background template designs."""

import io
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw

from app.newsbite.renderer import render
from app.newsbite.schema import NewsBite


def generate():
    out = Path("/app/tests/generated-newsbite/correction")
    out.mkdir(parents=True, exist_ok=True)
    photo = Image.open("/tmp/bnc-newsroom-photo.png")
    sheet = Image.new("RGB", (1080, 740), "#d9dfe6")
    for row, template in enumerate(("dark-editorial", "breaking-news")):
        for column, version in enumerate((1, 2)):
            config = NewsBite(
                template_id=template,
                template_version=version,
                layout_version=version,
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
            png, result = render(config, photo)
            assert not result["errors"], result["errors"]
            (out / f"{template}-v{version}.png").write_bytes(png)
            img = Image.open(io.BytesIO(png))
            img.thumbnail((540, 338))
            sheet.paste(img, (column * 540 + (540 - img.width) // 2, row * 370))
            ImageDraw.Draw(sheet).text(
                (column * 540 + 15, row * 370 + 342),
                f"{template} / version {version}",
                fill="black",
            )
    sheet.save(out / "before-after.png")


if __name__ == "__main__":
    generate()
