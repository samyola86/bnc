"""One Pillow/Raqm scene produces both the live preview and saved PNG.

All geometry is in 1080x1350 output pixels. No browser screenshots or remote fonts.
"""

import io
import math
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps, features

from .schema import NewsBite

WIDTH, HEIGHT = 1080, 1350
FONTS = Path(__file__).parent / "fonts"


@dataclass(frozen=True)
class Template:
    name: str
    background: str
    ink: str
    accent: str
    x: int
    width: int
    top: int
    bottom: int
    headline_preferred: int
    headline_min: int
    headline_max_height: int
    support_preferred: int = 30
    support_min: int = 24
    support_max_height: int = 220
    image_min: int = 280
    image_preferred: int = 480
    image_max: int = 650
    gap: int = 24
    headline_min_height: int = 100
    max_lines: int = 10
    alignment: str = "left"
    overflow: str = "block export; shorten text or change template"
    priority: str = "reserve branding/credits; grow text; shrink photo; shrink type"


TEMPLATES = {
    "newspaper": Template(
        "BNC Newspaper", "#f4efdf", "#12151a", "#123e8b", 64, 952, 245, 1185, 64, 40, 620
    ),
    "dark-editorial": Template(
        "BNC Dark Editorial", "#101827", "#ffffff", "#ff535a", 70, 940, 180, 1170, 70, 42, 660
    ),
    "breaking-news": Template(
        "BNC Breaking News",
        "#101725",
        "#ffffff",
        "#61b9ff",
        206,
        810,
        190,
        1180,
        66,
        40,
        650,
        image_min=300,
    ),
    "modern-magazine": Template(
        "BNC Modern Magazine",
        "#e85a00",
        "#ffffff",
        "#ff791c",
        129,
        450,
        347,
        1028,
        132,
        38,
        500,
        image_min=1350,
        image_preferred=1350,
        image_max=1350,
        support_max_height=300,
    ),
}


@lru_cache(maxsize=100)
def font(size, serif=False):
    if not features.check("raqm"):
        raise RuntimeError("Raqm text shaping is required. Install libraqm0 and restart the API.")
    result = ImageFont.truetype(
        str(FONTS / ("NotoSerifBengali.ttf" if serif else "NotoSansBengali.ttf")),
        size,
        layout_engine=ImageFont.Layout.RAQM,
    )
    result.set_variation_by_axes([800 if size >= 38 else 400, 100])
    return result


def wrap(text, face, width):
    """Keep exact source offsets for multi-line emphasis; never split shaped words."""
    lines = []
    start, current = 0, ""
    for match in re.finditer(r"\S+[^\S\n]*|\n", text):
        token = match.group()
        if token == "\n":
            lines.append((current.rstrip(), start))
            current, start = "", match.end()
        elif current and face.getlength((current + token).rstrip()) > width:
            lines.append((current.rstrip(), start))
            current, start = token, match.start()
        else:
            if not current:
                start = match.start()
            current += token
    if current:
        lines.append((current.rstrip(), start))
    return lines


def block(text, size, width, serif=False):
    face = font(size, serif)
    lines = wrap(text, face, width)
    # Use font metrics, including Bengali ascenders/descenders, as the line box.
    step = math.ceil(sum(face.getmetrics()) * 1.06)
    return {
        "lines": lines,
        "size": size,
        "step": step,
        "height": len(lines) * step,
        "wide": any(face.getlength(line) > width for line, _ in lines),
    }


def layout(config, category="", photo_credit=""):
    if config.template_id == "modern-magazine":
        from .magazine import layout as magazine_layout

        return magazine_layout(config, category, photo_credit)
    if config.template_id == "newspaper" and config.template_version == 2:
        from .newspaper import layout as newspaper_layout

        return newspaper_layout(config, category, photo_credit)
    if (
        config.template_version == 2
        and config.layout_version == 2
        and config.template_id in {"dark-editorial", "breaking-news"}
    ):
        from .photographic import layout as photographic_layout

        return photographic_layout(config, category, photo_credit)
    t = TEMPLATES[config.template_id]
    errors = []
    if not config.headline.strip():
        errors.append("Add a graphic headline.")
    if not config.publication_date:
        errors.append("Choose a publication date.")
    # Attribution and footer are measured, reserved, and never sacrificed to headlines.
    credits = "\n".join(filter(None, [config.speaker, config.source_credit, photo_credit]))
    credit = block(credits, 23, t.width)
    footer = block(config.footer, 22, t.width)
    category_block = block(
        category, 24, t.width - 40 if config.template_id == "modern-magazine" else t.width
    )
    if (
        credit["height"] > 160
        or footer["height"] > 100
        or category_block["height"] > 80
        or any(b["wide"] for b in [credit, footer, category_block])
    ):
        errors.append("Attribution, category or footer is too long. Shorten these fields.")
    budget = t.bottom - t.top - category_block["height"] - t.gap
    found = None
    for size in range(t.headline_preferred, t.headline_min - 1, -1):
        head = block(config.headline, size, t.width, config.template_id == "newspaper")
        # Preserve headline hierarchy; shrink supporting text within its own bounds.
        support_size = max(t.support_min, round(t.support_preferred * size / t.headline_preferred))
        support = block(config.supporting, support_size, t.width)
        fixed = (
            max(t.headline_min_height, head["height"])
            + support["height"]
            + credit["height"]
            + 3 * t.gap
        )
        image_height = min(t.image_max, max(t.image_min, budget - fixed))
        fits = (
            fixed + image_height <= budget
            and head["height"] <= t.headline_max_height
            and support["height"] <= t.support_max_height
            and len(head["lines"]) <= t.max_lines
            and not head["wide"]
            and not support["wide"]
        )
        if fits:
            found = {
                "headline": head,
                "supporting": support,
                "credits": credit,
                "footer": footer,
                "category": category_block,
                "image_height": image_height,
                "headline_height": max(t.headline_min_height, head["height"]),
            }
            break
    if found is None:
        errors.append(
            "Text does not fit safely. Shorten the headline/description or select another template."
        )
    return found, errors


def draw_block(
    canvas, draw, value, x, y, color, width, *, serif=False, highlight=None, accent=None
):
    face = font(value["size"], serif)
    for line, offset in value["lines"]:
        draw.text((x, y), line, font=face, fill=color, anchor="lt")
        if highlight:
            lo, hi = max(0, highlight[0] - offset), min(len(line), highlight[1] - offset)
            if hi > lo:
                # Repaint the whole shaped line in accent through a range mask.
                layer = Image.new("RGBA", (WIDTH, HEIGHT))
                ImageDraw.Draw(layer).text((x, y), line, font=face, fill=accent, anchor="lt")
                mask = Image.new("L", (WIDTH, HEIGHT))
                left = x + face.getlength(line[:lo])
                right = x + face.getlength(line[:hi])
                ImageDraw.Draw(mask).rectangle((left, y, right, y + value["step"] - 1), fill=255)
                from PIL import ImageChops

                canvas.paste(layer, (0, 0), ImageChops.multiply(layer.getchannel("A"), mask))
        y += value["step"]
    return y


def render(config: NewsBite, photo=None, category="", photo_credit=""):
    if config.template_id == "modern-magazine":
        from .magazine import render as magazine_render

        return magazine_render(config, photo, category, photo_credit)
    if config.template_id == "newspaper" and config.template_version == 2:
        from .newspaper import render as newspaper_render

        return newspaper_render(config, photo, category, photo_credit)
    if (
        config.template_version == 2
        and config.layout_version == 2
        and config.template_id in {"dark-editorial", "breaking-news"}
    ):
        from .photographic import render as photographic_render

        return photographic_render(config, photo, category, photo_credit)
    t = TEMPLATES[config.template_id]
    scene, errors = layout(config, category, photo_credit)
    warnings = []
    canvas = Image.new("RGB", (WIDTH, HEIGHT), t.background)
    d = ImageDraw.Draw(canvas)
    if config.template_id == "newspaper":
        # Procedural, deterministic paper grain; no reference screenshot is used.
        for y in range(0, HEIGHT, 6):
            for x in range((y * 7) % 13, WIDTH, 19):
                d.point((x, y), fill="#ddd8c9")
        d.line((64, 27, 1016, 27), fill=t.ink, width=3)
        d.text((64, 42), "BNC NEWS", font=font(150, True), fill=t.ink, anchor="lt")
        d.text((68, 166), "BANGLADESH NEWS CORPORATION", font=font(26), fill=t.ink, anchor="lt")
        d.line((64, 196, 1016, 196), fill=t.ink, width=3)
        d.line((64, 230, 1016, 230), fill=t.ink, width=1)
    else:
        if config.template_id == "modern-magazine":
            d.polygon([(0, 1050), (1080, 550), (1080, 950), (0, 1350)], fill="#f2f1ee")
            d.rounded_rectangle((54, 150, 1026, 1294), radius=42, fill="#ffffff")
        if config.template_id == "breaking-news":
            d.rectangle((0, 0, 144, HEIGHT), fill="#b5122d")
            side = Image.new("RGB", (HEIGHT, 144), "#b5122d")
            ImageDraw.Draw(side).text(
                (65, 15),
                "BREAKING NEWS",
                font=font(110),
                fill="#b5122d",
                stroke_width=2,
                stroke_fill="#eb6979",
                anchor="lt",
            )
            canvas.paste(side.rotate(90, expand=True), (0, 0))
        d.text((t.x, 45), "BNC", font=font(68), fill="white", anchor="lt")
        d.text(
            (t.x + 170, 63), "BANGLADESH NEWS CORPORATION", font=font(19), fill="white", anchor="lt"
        )
        d.line((t.x, 130, t.x + t.width, 130), fill="#ec3044", width=3)
    date_text = config.publication_date.isoformat() if config.publication_date else "DATE REQUIRED"
    if config.template_id == "newspaper":
        d.text((t.x, 203), date_text, font=font(19), fill=t.ink, anchor="lt")
        d.text((775, 203), "BNC NEWSROOM", font=font(19), fill=t.ink, anchor="lt")
    else:
        d.text(
            (t.x + t.width - 170, 145),
            date_text,
            font=font(21),
            fill=t.ink if config.template_id == "modern-magazine" else "white",
            anchor="lt",
        )
    if errors:
        d.text((t.x, 420), "CONTENT NEEDS EDITING", font=font(35), fill=t.accent, anchor="lt")
        # Never create a seemingly valid clipped graphic from overflowing text.
    elif scene:
        x, y, w = t.x, t.top, t.width
        d = ImageDraw.Draw(canvas)
        if config.template_id == "modern-magazine" and category:
            pill_width = min(w, int(font(24).getlength(category)) + 40)
            d.rounded_rectangle(
                (x, y - 8, x + pill_width, y + scene["category"]["height"]),
                radius=20,
                fill="#c5152b",
            )
            draw_block(canvas, d, scene["category"], x + 20, y, "white", w)
            y += scene["category"]["height"] + t.gap
        else:
            y = draw_block(canvas, d, scene["category"], x, y, t.accent, w) + t.gap
        image_first = config.template_id in {"dark-editorial", "breaking-news", "modern-magazine"}
        head_y = y + scene["image_height"] + t.gap if image_first else y
        image_y = (
            y
            if image_first
            else y
            + scene["headline_height"]
            + scene["supporting"]["height"]
            + scene["credits"]["height"]
            + 3 * t.gap
        )
        frame = (x, image_y, x + w, image_y + scene["image_height"])
        if photo is not None:
            if photo.width < w or photo.height < scene["image_height"]:
                warnings.append(
                    "Low-resolution photograph: use a larger original for sharp export."
                )
            crop = ImageOps.fit(
                ImageOps.exif_transpose(photo).convert("RGB"),
                (w, scene["image_height"]),
                method=Image.Resampling.LANCZOS,
                centering=(config.focal_x, config.focal_y),
            )
            mask = Image.new("L", crop.size, 255)
            if config.template_id == "modern-magazine":
                mask = Image.new("L", crop.size)
                ImageDraw.Draw(mask).rounded_rectangle(
                    (0, 0, w, scene["image_height"]), radius=32, fill=255
                )
            if config.template_id in {"dark-editorial", "breaking-news"}:
                shade = Image.new("RGBA", crop.size)
                sd = ImageDraw.Draw(shade)
                for row in range(crop.height):
                    sd.line((0, row, w, row), fill=(8, 16, 30, int(160 * (row / crop.height) ** 2)))
                crop = Image.alpha_composite(crop.convert("RGBA"), shade).convert("RGB")
            canvas.paste(crop, (x, image_y), mask)
        else:
            d.rectangle(frame, fill="#293649")
            d.text(
                (x + 30, image_y + 40),
                "Add a permitted photograph",
                font=font(28),
                fill="white",
                anchor="lt",
            )
        d = ImageDraw.Draw(canvas)
        if config.template_id in {"dark-editorial", "breaking-news"}:
            d.arc(
                (x - 200, image_y - 50, x + w, image_y + scene["image_height"] + 140),
                170,
                320,
                fill="#7b8494",
                width=1,
            )
            d.line((x, head_y - 12, x + 80, head_y - 12), fill="#e61932", width=5)
        if config.template_id in {"newspaper", "modern-magazine"}:
            d.text((x - 40, head_y - 22), "“", font=font(38), fill=t.accent, anchor="lt")
        start = config.headline.find(config.highlight) if config.highlight else -1
        draw_block(
            canvas,
            d,
            scene["headline"],
            x,
            head_y,
            t.ink,
            w,
            serif=config.template_id == "newspaper",
            highlight=(start, start + len(config.highlight)) if start >= 0 else None,
            accent=t.accent,
        )
        sy = head_y + scene["headline_height"] + t.gap
        sy = draw_block(canvas, d, scene["supporting"], x, sy, t.ink, w) + t.gap
        draw_block(canvas, d, scene["credits"], x, sy, t.ink, w)
        draw_block(
            canvas,
            d,
            scene["footer"],
            x,
            1220,
            t.ink if config.template_id != "modern-magazine" else "#222222",
            w,
        )
        if config.template_id == "modern-magazine":
            for i in range(4):
                d.ellipse(
                    (470 + i * 36, 1308, 482 + i * 36, 1320), fill="white" if i == 0 else "#e87986"
                )
    out = io.BytesIO()
    canvas.save(out, "PNG", optimize=True)
    return out.getvalue(), {
        "errors": errors,
        "warnings": warnings,
        "layout": scene,
        "width": WIDTH,
        "height": HEIGHT,
    }


def definitions():
    values = [
        {"id": key, "version": 1, "layout_version": 1, **asdict(value)}
        for key, value in TEMPLATES.items()
    ]
    for value in values:
        if value["id"] in {"dark-editorial", "breaking-news"}:
            breaking = value["id"] == "breaking-news"
            value.update(
                version=2,
                layout_version=2,
                legacy_versions=[1],
                full_bleed=True,
                x=320 if breaking else 68,
                width=700 if breaking else 884,
                headline_preferred=68 if breaking else 80,
                headline_min=44,
                image_min=300,
                image_max=615,
                top=180,
                bottom=1220,
                priority="reserve header/footer; fit text above minimum clear photo zone",
            )
    for value in values:
        if value["id"] == "modern-magazine":
            from .magazine import PANEL

            value.update(
                full_bleed=True,
                panel=PANEL,
                category_color="#ff791c",
                priority="reserve branding/category; fit writing within frosted panel",
            )
        if value["id"] == "newspaper":
            from .newspaper import GRID

            value.update(
                version=2,
                layout_version=2,
                legacy_versions=[1],
                x=GRID["x"],
                width=GRID["right"] - GRID["x"] + 1,
                top=GRID["story_top"],
                bottom=GRID["bottom"],
                headline_preferred=GRID["headline_preferred"],
                headline_min=GRID["headline_min"],
                image_min=GRID["image_min"],
                image_max=GRID["image_max"],
                gap=GRID["gap"],
                max_lines=8,
                grid=GRID,
            )
    return values
