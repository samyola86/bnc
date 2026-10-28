"""Modern Magazine: full photo, frosted left panel and orange news category."""

import io

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from .newspaper import face, measure, tracked_text, visible_text
from .photographic import spaced
from .renderer import HEIGHT, WIDTH

PANEL = (66, 260, 635, 1074)
TEXT_X, TEXT_WIDTH, TEXT_TOP, TEXT_BOTTOM = 129, 450, 347, 1028
ORANGE = "#ff791c"


def layout(config, category="", photo_credit=""):
    errors = []
    if not config.headline.strip():
        errors.append("Add a graphic headline.")
    if not config.publication_date:
        errors.append("Choose a publication date.")
    if not category.strip():
        errors.append("Add a news category for the orange category tag.")
    tag = measure(category.upper(), 42, TEXT_WIDTH)
    credits = "\n".join(filter(None, [config.speaker, config.source_credit, photo_credit]))
    credit = measure(credits, 20, TEXT_WIDTH, "body")
    footer = measure(config.footer, 19, TEXT_WIDTH, "body")
    if (
        tag["height"] > 120
        or credit["height"] > 110
        or footer["height"] > 80
        or any(b["wide"] for b in [tag, credit, footer])
    ):
        errors.append("Category, attribution or footer is too long. Shorten these fields.")
    for size in range(132, 37, -1):
        headline = measure(config.headline, size, TEXT_WIDTH)
        supporting = measure(
            config.supporting, max(24, min(36, round(size * 0.30))), TEXT_WIDTH, "body"
        )
        y = TEXT_TOP
        positions = {"headline": y}
        y += headline["height"] + 28
        rule_y = y
        y += 34
        positions["category"] = y
        if tag["height"]:
            y += tag["height"] + 34
        positions["supporting"] = y
        if supporting["height"]:
            y += supporting["height"] + 22
        positions["credits"] = y
        if credit["height"]:
            y += credit["height"] + 16
        positions["footer"] = y
        y += footer["height"]
        if (
            y <= TEXT_BOTTOM
            and headline["height"] <= 500
            and len(headline["lines"]) <= 8
            and supporting["height"] <= 300
            and not headline["wide"]
            and not supporting["wide"]
        ):
            return {
                "headline": headline,
                "supporting": supporting,
                "category": tag,
                "credits": credit,
                "footer": footer,
                "positions": positions,
                "rule_y": rule_y,
                "panel": PANEL,
                "photo_frame": (0, 0, WIDTH, HEIGHT),
                "image_height": HEIGHT,
                "headline_height": headline["height"],
            }, errors
    return None, [
        *errors,
        "Text does not fit safely. Shorten the headline/description or select another template.",
    ]


def draw_text(canvas, block, text, y, color="white", highlight=""):
    f = face(text, block["size"], block["role"])
    start = text.find(highlight) if highlight else -1
    for line, offset in block["lines"]:
        d = ImageDraw.Draw(canvas)
        x = TEXT_X - f.getbbox(line, anchor="lt")[0]
        d.text((x, y), line, font=f, fill=color, anchor="lt")
        lo, hi = max(0, start - offset), min(len(line), start + len(highlight) - offset)
        if start >= 0 and hi > lo:
            layer = Image.new("RGBA", canvas.size)
            ImageDraw.Draw(layer).text((x, y), line, font=f, fill="#61b9ff", anchor="lt")
            mask = Image.new("L", canvas.size)
            ImageDraw.Draw(mask).rectangle(
                (x + f.getlength(line[:lo]), y, x + f.getlength(line[:hi]), y + block["step"] - 1),
                fill=255,
            )
            canvas.paste(layer, (0, 0), ImageChops.multiply(mask, layer.getchannel("A")))
        y += block["step"]


def render(config, photo=None, category="", photo_credit=""):
    scene, errors = layout(config, category, photo_credit)
    warnings = []
    if photo is not None:
        oriented = ImageOps.exif_transpose(photo).convert("RGB")
        if oriented.width < WIDTH or oriented.height < HEIGHT:
            warnings.append("Low-resolution photograph: use a larger original for sharp export.")
        canvas = ImageOps.fit(
            oriented,
            (WIDTH, HEIGHT),
            Image.Resampling.LANCZOS,
            centering=(config.focal_x, config.focal_y),
        )
    else:
        canvas = Image.new("RGB", (WIDTH, HEIGHT), "#e85a00")
        warnings.append("Add a permitted photograph for the full-background design.")
    # A local frosted-glass panel blurs the same focal crop, without changing it.
    panel_mask = Image.new("L", canvas.size)
    ImageDraw.Draw(panel_mask).rounded_rectangle(PANEL, radius=72, fill=255)
    blurred = canvas.filter(ImageFilter.GaussianBlur(19))
    blurred = Image.blend(blurred, Image.new("RGB", canvas.size, "#100e0c"), 0.55)
    canvas.paste(blurred, (0, 0), panel_mask)
    shade = Image.new("RGBA", canvas.size)
    sd = ImageDraw.Draw(shade)
    for y in range(1100, HEIGHT):
        sd.line((0, y, WIDTH, y), fill=(0, 0, 0, round(150 * (y - 1100) / 250)))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), shade).convert("RGB")
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle(PANEL, radius=72, outline="#e9ccb3", width=2)
    brand = "BANGLADESH NEWS CORPORATION"
    # Native condensed glyphs with reference-style tracking, never stretched.
    tracked_text(d, brand, face(brand, 39), 46, 580, fill="white")
    visible_text(d, "BNC NEWS", face("BNC NEWS", 84), WIDTH / 2, 1180, align="center", fill="white")
    spaced(d, (540, 1273), "BNCNEWS.NET", 22, 5, anchor="center")
    if scene and not errors:
        texts = {
            "headline": config.headline,
            "category": category.upper(),
            "supporting": config.supporting,
            "credits": "\n".join(
                filter(None, [config.speaker, config.source_credit, photo_credit])
            ),
            "footer": config.footer,
        }
        for key, text in texts.items():
            draw_text(
                canvas,
                scene[key],
                text,
                scene["positions"][key],
                color=ORANGE if key == "category" else "white",
                highlight=config.highlight if key == "headline" else "",
            )
        d.rounded_rectangle(
            (TEXT_X, scene["rule_y"], TEXT_X + 76, scene["rule_y"] + 12), radius=4, fill=ORANGE
        )
    else:
        d.text((TEXT_X, 400), "CONTENT NEEDS EDITING", font=face("CONTENT", 30), fill="white")
    out = io.BytesIO()
    canvas.save(out, "PNG", optimize=True)
    return out.getvalue(), {
        "errors": errors,
        "warnings": warnings,
        "layout": scene,
        "width": WIDTH,
        "height": HEIGHT,
    }
