"""Newspaper v2. Reference measurements normalized from 1254px to 1080px.

Licensed font approximations, not an assertion of the reference's font identity.
Legacy v1 stays in renderer.py. All measurements describe visible glyph bounds.
"""

import io
import random
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

from .renderer import FONTS, HEIGHT, WIDTH, font, wrap

GRID = {
    "x": 51,
    "right": 1029,
    "top_rule": 39,
    "top_weight": 5,
    "masthead_y": 66,
    "masthead_width": 940,
    "masthead_height": 130,
    "masthead_center": 545,
    "corporation_y": 219,
    "corporation_width": 770,
    "corporation_rule": 261,
    "corporation_weight": 5,
    "metadata_y": 278,
    "metadata_size": 23,
    "metadata_rule": 308,
    "double_rule": 320,
    "story_top": 345,
    "bottom": 1299,
    "photo_gap": 17,
    "photo_border": 2,
    "separator_weight": 2,
    "gap": 18,
    "headline_preferred": 129,
    "headline_min": 40,
    "image_min": 280,
    "image_max": 900,
}
INK, ACCENT = "#10100e", "#123e8b"


@lru_cache(maxsize=160)
def latin(size, role="headline"):
    name = {
        "headline": "Anton-Regular.ttf",
        "masthead": "DMSerifDisplay-Regular.ttf",
        "serif": "LibreBaskerville.ttf",
        "body": "Poppins-Regular.ttf",
    }[role]
    result = ImageFont.truetype(str(FONTS / name), size, layout_engine=ImageFont.Layout.RAQM)
    if role == "serif":
        result.set_variation_by_axes([700])
    return result


def face(text, size, role="headline"):
    # Select one shaped face for the whole mixed Bengali/English block.
    if any("\u0980" <= char <= "\u09ff" for char in text):
        return font(size, role == "serif")
    return latin(size, role)


def measure(text, size, width, role="headline"):
    f = face(text, size, role)
    lines = wrap(text, f, width)
    glyph = max((f.getbbox(line, anchor="lt")[3] for line, _ in lines), default=0)
    # Cap-height-led English spacing; Bengali reserves the full shaped glyph height.
    step = glyph + max(8, round(size * (0.16 if role == "headline" else 0.10)))
    height = (len(lines) - 1) * step + glyph if lines else 0
    return {
        "lines": lines,
        "size": size,
        "step": step,
        "height": height,
        "wide": any(f.getbbox(line)[2] - f.getbbox(line)[0] > width for line, _ in lines),
        "role": role,
    }


@lru_cache(maxsize=1)
def paper():
    rng = random.Random(20261024)
    grain = Image.frombytes("L", (WIDTH, HEIGHT), rng.randbytes(WIDTH * HEIGHT))
    clouds = Image.frombytes("L", (135, 169), rng.randbytes(135 * 169))
    clouds = clouds.resize((WIDTH, HEIGHT), Image.Resampling.BICUBIC).filter(
        ImageFilter.GaussianBlur(4)
    )
    canvas = Image.new("RGB", (WIDTH, HEIGHT), (244, 239, 226))
    canvas = Image.blend(canvas, ImageOps.colorize(clouds, "#d9cfba", "#fffdf5"), 0.18)
    return Image.blend(canvas, ImageOps.colorize(grain, "#cfc6b4", "#ffffff"), 0.10)


@lru_cache(maxsize=512)
def ink_bounds(text, f, stroke=0):
    mask, offset = f.getmask2(text, mode="L", anchor="lt", stroke_width=stroke)
    bounds = Image.frombytes("L", mask.size, bytes(mask)).getbbox()
    if bounds is None:
        return (0, 0, round(f.getlength(text)), 0)
    return tuple(bounds[i] + offset[i % 2] for i in range(4))


def visible_text(draw, text, f, x, y, *, align="left", fill=INK, stroke=0):
    box = ink_bounds(text, f, stroke)
    width = box[2] - box[0]
    left = x - width if align == "right" else x - width / 2 if align == "center" else x
    draw.text(
        (left - box[0], y - box[1]),
        text,
        font=f,
        fill=fill,
        anchor="lt",
        stroke_width=stroke,
        stroke_fill=fill,
    )
    return (round(left), y, round(left + width), y + box[3] - box[1])


def tracked_text(draw, text, f, y, width, *, stroke=0, center=WIDTH / 2, fill=INK):
    boxes = [ink_bounds(c, f, stroke) for c in text]
    widths = [b[2] - b[0] for b in boxes]
    spacing = (width - sum(widths)) / (len(text) - 1)
    cursor = center - width / 2
    bottom = y
    for char, char_width in zip(text, widths, strict=True):
        bounds = visible_text(draw, char, f, cursor, y, stroke=stroke, fill=fill)
        bottom = max(bottom, bounds[3])
        cursor += char_width + spacing
    return (round(center - width / 2), y, round(center + width / 2), bottom)


def header(canvas, config):
    d = ImageDraw.Draw(canvas)
    x, right = GRID["x"], GRID["right"]
    d.rectangle((x, GRID["top_rule"], right, GRID["top_rule"] + GRID["top_weight"] - 1), fill=INK)
    size = 220
    while True:
        f = latin(size, "masthead")
        bounds = ink_bounds("BNC NEWS", f, 2)
        if (
            bounds[2] - bounds[0] <= GRID["masthead_width"]
            and bounds[3] - bounds[1] <= GRID["masthead_height"]
        ):
            break
        size -= 1
    masthead = tracked_text(
        d,
        "BNC NEWS",
        f,
        GRID["masthead_y"],
        GRID["masthead_width"],
        stroke=2,
        center=GRID["masthead_center"],
    )
    text = "BANGLADESH NEWS CORPORATION"
    f = latin(30, "serif")
    corporation = tracked_text(d, text, f, GRID["corporation_y"], GRID["corporation_width"])
    d.rectangle(
        (
            x,
            GRID["corporation_rule"],
            right,
            GRID["corporation_rule"] + GRID["corporation_weight"] - 1,
        ),
        fill=INK,
    )
    when = config.publication_date
    date_text = when.strftime("%A, %B %d %Y").upper() if when else "DATE REQUIRED"
    metadata = latin(GRID["metadata_size"], "serif")
    date_bounds = visible_text(d, date_text, metadata, x, GRID["metadata_y"])
    site_bounds = visible_text(
        d, "BNCNEWS.NET", metadata, right + 1, GRID["metadata_y"], align="right"
    )
    for y, weight in [(GRID["metadata_rule"], 3), (GRID["double_rule"], 2)]:
        d.rectangle((x, y, right, y + weight - 1), fill=INK)
    return {
        "masthead": masthead,
        "date": date_bounds,
        "website": site_bounds,
        "corporation": corporation,
    }


def layout(config, category="", photo_credit=""):
    w = GRID["right"] - GRID["x"] + 1
    errors = []
    if not config.headline.strip():
        errors.append("Add a graphic headline.")
    if not config.publication_date:
        errors.append("Choose a publication date.")
    credits = "\n".join(filter(None, [config.speaker, config.source_credit, photo_credit]))
    extra = {
        "category": measure(category, 24, w, "serif"),
        "credits": measure(credits, 23, w, "body"),
        "footer": measure(config.footer, 22, w, "body"),
    }
    if any(b["wide"] for b in extra.values()) or any(
        extra[k]["height"] > limit
        for k, limit in [("category", 80), ("credits", 160), ("footer", 100)]
    ):
        errors.append("Attribution, category or footer is too long. Shorten these fields.")
    for size in range(GRID["headline_preferred"], GRID["headline_min"] - 1, -1):
        head = measure(config.headline, size, w)
        support = measure(config.supporting, max(24, min(30, round(size * 0.3))), w, "body")
        blocks = {
            "category": extra["category"],
            "headline": head,
            "supporting": support,
            "credits": extra["credits"],
        }
        y, positions = GRID["story_top"], {}
        for key, block in blocks.items():
            positions[key] = y
            if block["height"]:
                y += block["height"] + GRID["gap"]
        separator_y = y
        photo_y = separator_y + GRID["photo_gap"]
        footer_space = extra["footer"]["height"] + GRID["gap"] if extra["footer"]["height"] else 0
        image_height = min(GRID["image_max"], GRID["bottom"] - photo_y - footer_space)
        if (
            image_height >= GRID["image_min"]
            and head["height"] <= 650
            and support["height"] <= 220
            and len(head["lines"]) <= 8
            and not head["wide"]
            and not support["wide"]
        ):
            return {
                **blocks,
                "footer": extra["footer"],
                "positions": positions,
                "headline_height": head["height"],
                "image_height": image_height,
                "separator_y": separator_y,
                "photo_frame": (GRID["x"], photo_y, GRID["right"] + 1, photo_y + image_height),
                "footer_y": photo_y + image_height + GRID["gap"],
            }, errors
    return None, [
        *errors,
        "Text does not fit safely. Shorten the headline/description or select another template.",
    ]


def draw_block(canvas, block, text, y, *, highlight="", color=INK):
    f = face(text, block["size"], block["role"])
    start = text.find(highlight) if highlight else -1
    x = GRID["x"]
    for line, offset in block["lines"]:
        d = ImageDraw.Draw(canvas)
        box = f.getbbox(line, anchor="lt")
        origin = x - box[0]
        d.text((origin, y), line, font=f, fill=color, anchor="lt")
        lo, hi = max(0, start - offset), min(len(line), start + len(highlight) - offset)
        if start >= 0 and hi > lo:
            layer = Image.new("RGBA", canvas.size)
            ImageDraw.Draw(layer).text((origin, y), line, font=f, fill=ACCENT, anchor="lt")
            mask = Image.new("L", canvas.size)
            ImageDraw.Draw(mask).rectangle(
                (
                    origin + f.getlength(line[:lo]),
                    y,
                    origin + f.getlength(line[:hi]),
                    y + block["step"] - 1,
                ),
                fill=255,
            )
            canvas.paste(layer, (0, 0), ImageChops.multiply(layer.getchannel("A"), mask))
        y += block["step"]


def render(config, photo=None, category="", photo_credit=""):
    canvas = paper().copy()
    bounds = header(canvas, config)
    scene, errors = layout(config, category, photo_credit)
    warnings = []
    if scene and not errors:
        texts = {
            "category": category,
            "headline": config.headline,
            "supporting": config.supporting,
            "credits": "\n".join(
                filter(None, [config.speaker, config.source_credit, photo_credit])
            ),
        }
        for key, text in texts.items():
            draw_block(
                canvas,
                scene[key],
                text,
                scene["positions"][key],
                highlight=config.highlight if key == "headline" else "",
                color=ACCENT if key == "category" else INK,
            )
        x, y, right, bottom = scene["photo_frame"]
        w, h = right - x, bottom - y
        d = ImageDraw.Draw(canvas)
        d.rectangle(
            (
                x,
                scene["separator_y"],
                right - 1,
                scene["separator_y"] + GRID["separator_weight"] - 1,
            ),
            fill=INK,
        )
        if photo is not None:
            oriented = ImageOps.exif_transpose(photo).convert("RGB")
            if oriented.width < w or oriented.height < h:
                warnings.append(
                    "Low-resolution photograph: use a larger original for sharp export."
                )
            crop = ImageOps.fit(
                oriented,
                (w, h),
                method=Image.Resampling.LANCZOS,
                centering=(config.focal_x, config.focal_y),
            )
            canvas.paste(crop, (x, y))
        else:
            d.rectangle((x, y, right - 1, bottom - 1), fill="#293649")
            d.text((x + 24, y + 24), "Add a permitted photograph", font=font(28), fill="white")
        # Paint inside the frame; preserve the exact cover-crop dimensions/focal point.
        ImageDraw.Draw(canvas).rectangle(
            (x, y, right - 1, bottom - 1), outline=INK, width=GRID["photo_border"]
        )
        draw_block(canvas, scene["footer"], config.footer, scene["footer_y"])
    else:
        ImageDraw.Draw(canvas).text(
            (GRID["x"], 420), "CONTENT NEEDS EDITING", font=font(35), fill=ACCENT
        )
    out = io.BytesIO()
    canvas.save(out, "PNG", optimize=True)
    return out.getvalue(), {
        "errors": errors,
        "warnings": warnings,
        "layout": scene,
        "header_bounds": bounds,
        "width": WIDTH,
        "height": HEIGHT,
    }
