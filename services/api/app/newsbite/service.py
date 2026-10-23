import hashlib
import io
import json
import uuid

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError

from app.config import get_settings
from app.media.routes import MAX_BYTES, image, storage

from .renderer import render
from .schema import NewsBite


def fingerprint(content):
    values = {
        k: content.get(k)
        for k in (
            "news_bite",
            "cover_image_id",
            "image_caption",
            "category",
            "social_captions",
            "social_caption",
            "destinations",
        )
    }
    return hashlib.sha256(
        json.dumps(values, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def render_content(content):
    config = NewsBite.model_validate(content.get("news_bite") or {})
    photo = None
    if content.get("cover_image_id"):
        response = image(uuid.UUID(str(content["cover_image_id"])))
        try:
            photo = Image.open(io.BytesIO(response.body))
            photo.load()
        except (UnidentifiedImageError, OSError, ValueError):
            raise HTTPException(
                422, "Cannot decode the photograph. Upload a valid image again"
            ) from None
    try:
        return render(config, photo, content.get("category", ""), content.get("image_caption", ""))
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from None
    except OSError:
        raise HTTPException(
            503, "Graphic fonts could not load. Check the renderer installation"
        ) from None
    finally:
        if photo:
            photo.close()


def attach_render(version):
    """Only server-generated metadata is attached; clients cannot supply artifact IDs."""
    content = version.content_json
    content.pop("news_bite_render", None)
    if content.get("format") != "news_bite":
        return
    if not content.get("news_bite"):
        return  # Older/incomplete drafts remain editable, but cannot pass readiness.
    data, result = render_content(content)
    artifact = {
        "errors": result["errors"],
        "warnings": result["warnings"],
        "version_id": str(version.id),
        "fingerprint": fingerprint(content),
        "width": 1080,
        "height": 1350,
    }
    if not result["errors"] and content.get("cover_image_id"):
        asset_id = uuid.uuid4()
        if len(data) > MAX_BYTES:
            raise HTTPException(422, "Rendered graphic exceeds the media size limit")
        try:
            storage().put_object(
                Bucket=get_settings().s3_bucket,
                Key=f"covers/{asset_id}",
                Body=data,
                ContentType="image/png",
            )
        except (BotoCoreError, ClientError):
            raise HTTPException(
                503, "Graphic storage unavailable. Revision was not saved"
            ) from None
        artifact.update(asset_id=str(asset_id), sha256=hashlib.sha256(data).hexdigest())
    version.content_json = {**content, "news_bite_render": artifact}


def graphic_errors(content, version_id=None, *, verify_storage=False):
    errors = {}
    try:
        config = NewsBite.model_validate(content.get("news_bite") or {})
    except ValidationError:
        return {"news_bite": "Choose a valid template and highlighted headline segment"}
    _, result = render_layout_only(config, content)
    if result:
        errors["news_bite"] = " ".join(result)
    if not content.get("cover_image_id"):
        errors["cover_image_id"] = "Add a permitted photograph for the News Bite"
    if config.image_rights not in {"owned", "licensed"}:
        errors["news_bite_rights"] = "Confirm BNC-owned or licensed image rights"
    artifact = content.get("news_bite_render") or {}
    if (
        not artifact.get("asset_id")
        or artifact.get("errors")
        or artifact.get("width") != 1080
        or artifact.get("height") != 1350
        or artifact.get("fingerprint") != fingerprint(content)
        or (version_id and artifact.get("version_id") != str(version_id))
    ):
        errors["news_bite_render"] = "Save a successfully rendered graphic for this revision"
    elif verify_storage:
        response = image(uuid.UUID(artifact["asset_id"]))
        try:
            with Image.open(io.BytesIO(response.body)) as png:
                if (
                    png.format != "PNG"
                    or png.size != (1080, 1350)
                    or hashlib.sha256(response.body).hexdigest() != artifact.get("sha256")
                ):
                    errors["news_bite_render"] = (
                        "Saved graphic failed integrity verification; save again"
                    )
                png.verify()
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
            errors["news_bite_render"] = (
                "Saved graphic failed integrity verification; save again"
            )
    for channel in {"facebook", "instagram"} & set(content.get("destinations", [])):
        if not (
            content.get("social_captions", {}).get(channel, "").strip()
            or content.get("social_caption", "").strip()
        ):
            errors["social_captions"] = (
                "Add a caption for each selected Facebook/Instagram destination"
            )
    return errors


def render_layout_only(config, content):
    from .renderer import layout

    return layout(config, content.get("category", ""), content.get("image_caption", ""))
