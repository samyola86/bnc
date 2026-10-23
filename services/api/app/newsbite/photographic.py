"""Reference-led full-bleed photographic designs, version 2.

Version 1 remains available for immutable saved revisions. Coordinates are native
1080x1350 output pixels; photographs keep their aspect ratio.
"""

import io
import math
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

from .renderer import FONTS, HEIGHT, WIDTH, font, wrap

PHOTO_IDS = {"dark-editorial", "breaking-news"}
RAIL = 300


def curve(a, b, c, d):
    return [
        tuple(
            round(
                (1 - t) ** 3 * a[k]
                + 3 * (1 - t) ** 2 * t * b[k]
                + 3 * (1 - t) * t * t * c[k]
                + t**3 * d[k]
            )
            for k in (0, 1)
        )
        for t in (n / 60 for n in range(61))
    ]


@lru_cache(maxsize=100)
def latin(size, bold=False):
    name = "Poppins-ExtraBold.ttf" if bold else "Poppins-Regular.ttf"
    return ImageFont.truetype(str(FONTS / name), size, layout_engine=ImageFont.Layout.RAQM)


def face(text, size, bold=False):
    return (
        bengali(size, bold) if any("\u0980" <= c <= "\u09ff" for c in text) else latin(size, bold)
    )


@lru_cache(maxsize=100)
def bengali(size, bold=False):
    font(size)  # Fail clearly if the required shaping library is unavailable.
    result = ImageFont.truetype(
        str(FONTS / "NotoSansBengali.ttf"), size, layout_engine=ImageFont.Layout.RAQM
    )
    result.set_variation_by_axes([800 if bold else 400, 100])
    return result


def measure(text, size, width, bold=False):
    f = face(text, size, bold)
    lines = wrap(text, f, width)
    glyph_height = max((f.getbbox(line, anchor="lt")[3] for line, _ in lines), default=0)
    step = max(math.ceil(size * 1.12), glyph_height + max(6, size // 8))
    return {
        "lines": lines,
        "size": size,
        "step": step,
        "height": len(lines) * step,
        "wide": any(f.getlength(line) > width for line, _ in lines),
        "bold": bold,
        "bengali": any("\u0980" <= c <= "\u09ff" for c in text),
    }


def layout(config, category="", photo_credit=""):
    breaking = config.template_id == "breaking-news"
    x, width = (320, 700) if breaking else (68, 884)
    errors = []
    if not config.headline.strip():
        errors.append("Add a graphic headline.")
    if not config.publication_date:
        errors.append("Choose a publication date.")
    credits = "\n".join(filter(None, [config.source_credit, photo_credit]))
    attribution = measure(config.speaker, 25, width - 90)
    credit = measure(credits, 21, width)
    footer = measure("" if breaking else config.footer, 20, width - 100)
    if (
        attribution["height"] > 90
        or credit["height"] > 100
        or footer["height"] > 60
        or any(b["wide"] for b in [attribution, credit, footer])
    ):
        errors.append("Attribution or footer is too long. Shorten these fields.")
    scene = None
    # The photo occupies the entire canvas. Its clear subject zone above the
    # headline must remain at least 300px high, below the fixed header at y=180.
    bottom = 1220
    display_headline = config.headline
    if config.highlight:
        start = display_headline.find(config.highlight)
        if start > 0 and display_headline[start - 1].isspace():
            display_headline = display_headline[: start - 1] + "\n" + display_headline[start:]
    for size in range(68 if breaking else 80, 43, -1):
        headline = measure(display_headline, size, width, True)
        supporting = measure(config.supporting, max(27, round(size * 0.46)), width)
        parts = [headline, supporting, attribution, credit]
        gap = 24
        total = sum(p["height"] for p in parts) + gap * sum(bool(p["height"]) for p in parts)
        head_y = min(795, bottom - total)
        if (
            head_y >= 480
            and headline["height"] <= 650
            and len(headline["lines"]) <= 10
            and supporting["height"] <= 210
            and not headline["wide"]
            and not supporting["wide"]
        ):
            scene = {
                "x": x,
                "width": width,
                "head_y": head_y,
                "headline": headline,
                "supporting": supporting,
                "attribution": attribution,
                "credits": credit,
                "footer": footer,
                "image_height": head_y - 180,
                "headline_height": headline["height"],
                "category": measure("", 20, width),
                "photo_frame": [RAIL if breaking else 0, 0, WIDTH, HEIGHT],
                "gap": gap,
            }
            break
    if scene is None:
        errors.append(
            "Text does not fit safely. Shorten the headline/description or select another template."
        )
    return scene, errors


def spaced(draw, xy, text, size=22, tracking=3, fill="white", anchor="left"):
    f = latin(size)
    length = sum(f.getlength(c) for c in text) + max(0, len(text) - 1) * tracking
    x, y = xy
    if anchor == "center":
        x -= length / 2
    elif anchor == "right":
        x -= length
    for char in text:
        draw.text((x, y), char, font=f, fill=fill, anchor="lt")
        x += f.getlength(char) + tracking
    return length


def text_block(canvas, block, x, y, color="white", highlight=None, accent=None):
    draw = ImageDraw.Draw(canvas)
    for text, offset in block["lines"]:
        f = (
            bengali(block["size"], block["bold"])
            if block["bengali"]
            else latin(block["size"], block["bold"])
        )
        draw.text((x, y), text, font=f, fill=color, anchor="lt")
        if highlight:
            lo, hi = max(0, highlight[0] - offset), min(len(text), highlight[1] - offset)
            if hi > lo:
                layer = Image.new("RGBA", canvas.size)
                ImageDraw.Draw(layer).text((x, y), text, font=f, fill=accent, anchor="lt")
                mask = Image.new("L", canvas.size)
                ImageDraw.Draw(mask).rectangle(
                    (x + f.getlength(text[:lo]), y, x + f.getlength(text[:hi]), y + block["step"]),
                    fill=255,
                )
                canvas.paste(layer, (0, 0), ImageChops.multiply(mask, layer.getchannel("A")))
        y += block["step"]
    return y


@lru_cache(maxsize=1)
def quote_bubble():
    # Transparent 3x raster of the supplied SVG, including its gradients/glow.
    # Rasterized offline; runtime preview and export need only Pillow.
    path = Path(__file__).parent / "assets" / "BNC_Quote_Bubble.png"
    with Image.open(path) as source:
        return source.convert("RGBA").resize((205, 205), Image.Resampling.LANCZOS)


def render(config, photo, category="", photo_credit=""):
    breaking = config.template_id == "breaking-news"
    scene, errors = layout(config, category, photo_credit)
    warnings = []
    left = RAIL if breaking else 0
    canvas = Image.new("RGB", (WIDTH, HEIGHT), "#141b24")
    if photo:
        oriented = ImageOps.exif_transpose(photo).convert("RGB")
        if oriented.width < WIDTH - left or oriented.height < HEIGHT:
            warnings.append("Low-resolution photograph: use a larger original for sharp export.")
        crop = ImageOps.fit(
            oriented,
            (WIDTH - left, HEIGHT),
            Image.Resampling.LANCZOS,
            centering=(config.focal_x, config.focal_y),
        )
        canvas.paste(crop, (left, 0))
    else:
        ImageDraw.Draw(canvas).text(
            (left + 70, 400), "Add a permitted photograph", font=latin(30), fill="white"
        )
    head_y = scene["head_y"] if scene else 700
    shade = Image.new("RGBA", canvas.size)
    sd = ImageDraw.Draw(shade)
    # Header shade and a smooth, almost-black lower fade match the source designs.
    for y in range(HEIGHT):
        top = max(0, 1 - y / 350) * 205
        bottom = min(1, max(0, (y - (head_y - 300)) / 390))
        sd.line((left, y, WIDTH, y), fill=(5, 10, 17, round(max(top, bottom * 248))))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), shade)
    decoration = Image.new("RGBA", canvas.size)
    sd = ImageDraw.Draw(decoration)
    sd.polygon(
        [(0, 1350)] + curve((0, 1080), (40, 1200), (130, 1310), (260, 1350)), fill=(145, 0, 12, 55)
    )
    sd.polygon(
        [(1080, 1350)] + curve((780, 1350), (950, 1315), (1030, 1210), (1080, 1140)),
        fill=(160, 0, 12, 140),
    )
    canvas = Image.alpha_composite(canvas, decoration).convert("RGB")
    d = ImageDraw.Draw(canvas)
    d.arc((-250, 170, 650, 800), 160, 345, fill="#a0a2a4", width=1)
    d.arc((-180, 310, 570, 990), 180, 350, fill="#757a80", width=1)
    if breaking:
        rail = Image.new("RGB", (RAIL, HEIGHT))
        rd = ImageDraw.Draw(rail)
        for x in range(RAIL):
            rd.line((x, 0, x, HEIGHT), fill=(round(185 - 112 * x / RAIL), 0, 12))
        rd.ellipse((-130, -180, 560, 650), fill="#93000c")
        rd.ellipse((-150, 590, 410, 1100), fill="#71000a")
        lettering = Image.new("RGBA", (HEIGHT - 100, RAIL))
        size = 155
        while latin(size, True).getlength("BREAKING NEWS") > HEIGHT - 110:
            size -= 1
        f = latin(size, True)
        glyph_height = f.getbbox("BREAKING NEWS", anchor="lt")[3]
        ImageDraw.Draw(lettering).text(
            (0, (RAIL - glyph_height) // 2),
            "BREAKING NEWS",
            font=f,
            fill=(0, 0, 0, 0),
            stroke_width=2,
            stroke_fill="#ed6873",
            anchor="lt",
        )
        rail.paste(lettering.rotate(90, expand=True), (0, 50), lettering.rotate(90, expand=True))
        canvas.paste(rail, (0, 0))
        d = ImageDraw.Draw(canvas)
        for n in range(7):
            d.line((950, 460 + n * 14, 1080, 460 + n * 14), fill="white", width=2)
    brand = "BANGLADESH NEWS CORPORATION"
    brand_width = spaced(d, (540, 43), brand, 24, 4, anchor="center")
    edge = (WIDTH - brand_width) / 2
    d.line((68, 53, max(68, edge - 25), 53), fill="#c3c5c9", width=1)
    d.line((min(1012, WIDTH - edge + 25), 53, 1012, 53), fill="#c3c5c9", width=1)
    if not breaking:
        d.line((420, 76, 660, 76), fill="#d4d5d8", width=1)
    date = config.publication_date
    date_label = (
        (date.strftime("%B").upper() + f" {date.day}, {date.year}") if date else "DATE REQUIRED"
    )
    if breaking:
        spaced(d, (1010, 126), date_label, 22, 3, anchor="right")
        d.rectangle((926, 158, 1010, 163), fill="#ff1828")
    else:
        spaced(d, (68, 111), date_label, 22, 3)
        d.rectangle((68, 147, 158, 152), fill="#ff1828")
        bubble = quote_bubble()
        canvas.paste(bubble, (85, 182), bubble)
        vertical = Image.new("RGBA", (900, 55))
        spaced(
            ImageDraw.Draw(vertical),
            (0, 12),
            "FOLLOW US SO AS NOT TO MISS THE LATEST BREAKING NEWS",
            18,
            2,
        )
        canvas.paste(
            vertical.rotate(-90, expand=True), (990, 272), vertical.rotate(-90, expand=True)
        )
        d = ImageDraw.Draw(canvas)
        d.line((1018, 212, 1018, 257), fill="white", width=1)
        d.line((1018, 1154, 1018, 1198), fill="white", width=1)
        for n in range(4):
            d.ellipse(
                (1008, 1220 + n * 20, 1020, 1232 + n * 20), fill="#ff101e" if n == 0 else "white"
            )
    if errors:
        d.text(
            (left + 60, 650),
            "CONTENT NEEDS EDITING",
            font=latin(29, True),
            fill="white",
            anchor="lt",
        )
    elif scene:
        x, y = scene["x"], scene["head_y"]
        accent = "#23b5f4" if breaking else "#ff3044"
        if breaking:
            d.rectangle((x - 10, y - 22, x + 95, y - 14), fill="#ff1025")
        start = config.headline.find(config.highlight) if config.highlight else -1
        y = (
            text_block(
                canvas,
                scene["headline"],
                x,
                y,
                highlight=(start, start + len(config.highlight)) if start >= 0 else None,
                accent=accent,
            )
            + 24
        )
        order = (
            ["supporting", "attribution", "credits"]
            if breaking
            else ["attribution", "supporting", "credits"]
        )
        for key in order:
            value = scene[key]
            if not value["height"]:
                continue
            d = ImageDraw.Draw(canvas)
            if key == "attribution":
                d.rectangle((x + 4, y + 12, x + 65, y + 17), fill="#ff152b")
                text_block(canvas, value, x + 92, y)
            else:
                if key == "supporting" and breaking:
                    d.line((x + 95, y - 13, 1020, y - 13), fill="#cccccc", width=1)
                    for n in range(3):
                        d.ellipse((x + n * 24, y - 17, x + 10 + n * 24, y - 7), fill="white")
                text_block(canvas, value, x, y, color="#f4f4f4")
            y += value["height"] + 24
        if not breaking:
            d = ImageDraw.Draw(canvas)
            fy = min(1280, 1320 - scene["footer"]["height"])
            text_block(canvas, scene["footer"], x, fy, color="white")
            if len(scene["footer"]["lines"]) == 1:
                label = scene["footer"]["lines"][0][0]
                ax = x + face(label, 20).getlength(label) + 28
                d.line((ax, fy + 11, ax + 30, fy + 11), fill="white", width=2)
                d.line((ax + 20, fy + 2, ax + 30, fy + 11, ax + 20, fy + 20), fill="white", width=2)
                d.line((ax + 60, fy + 11, 1000, fy + 11), fill="#b6b7ba", width=1)
    out = io.BytesIO()
    canvas.save(out, "PNG", optimize=True)
    return out.getvalue(), {
        "errors": errors,
        "warnings": warnings,
        "layout": scene,
        "width": WIDTH,
        "height": HEIGHT,
    }
