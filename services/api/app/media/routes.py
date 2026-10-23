"""Private cover images, validated before writing to object storage."""

import base64
import binascii
import io
import uuid
import warnings

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from app.auth.editor import require_editor
from app.config import get_settings

router = APIRouter(prefix="/media", dependencies=[Depends(require_editor)], tags=["media"])
MAX_BYTES = 3 * 1024 * 1024
TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "GIF": "image/gif"}


def storage():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name="us-east-1",
    )


class Upload(BaseModel):
    data: str = Field(max_length=4 * 1024 * 1024)


@router.get("")
def library(cursor: str | None = Query(None, max_length=2048)):
    params = {"Bucket": get_settings().s3_bucket, "Prefix": "covers/", "MaxKeys": 24}
    if cursor:
        params["ContinuationToken"] = cursor
    try:
        result = storage().list_objects_v2(**params)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"InvalidArgument", "InvalidToken"}:
            raise HTTPException(422, "Invalid media cursor. Refresh the library") from None
        raise HTTPException(503, "Media storage unavailable") from None
    except BotoCoreError:
        raise HTTPException(503, "Media storage unavailable") from None
    items = []
    for obj in result.get("Contents", []):
        try:
            media_id = uuid.UUID(obj["Key"].removeprefix("covers/"))
        except ValueError:
            continue
        items.append({"id": str(media_id), "size": obj["Size"], "uploaded_at": obj["LastModified"]})
    return {"items": items, "next_cursor": result.get("NextContinuationToken")}


@router.post("", status_code=201)
def upload(body: Upload):
    try:
        data = base64.b64decode(body.data, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(422, "Invalid image encoding") from None
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(413, "Choose an image up to 3 MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                content_type = TYPES.get(image.format)
                if not content_type or image.width * image.height > 40_000_000:
                    raise ValueError()
                image.verify()
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ):
        raise HTTPException(
            422, "Choose a valid JPG, PNG, WebP or GIF up to 40 megapixels"
        ) from None
    media_id = uuid.uuid4()
    try:
        storage().put_object(
            Bucket=get_settings().s3_bucket,
            Key=f"covers/{media_id}",
            Body=data,
            ContentType=content_type,
        )
    except (BotoCoreError, ClientError):
        raise HTTPException(503, "Media storage unavailable. Your writing is unchanged") from None
    return {"id": str(media_id)}


@router.get("/{media_id}")
def image(media_id: uuid.UUID):
    try:
        result = storage().get_object(Bucket=get_settings().s3_bucket, Key=f"covers/{media_id}")
        with result["Body"] as stream:
            data = stream.read(MAX_BYTES + 1)
        if result["ContentType"] not in TYPES.values() or len(data) > MAX_BYTES:
            raise HTTPException(422, "Invalid stored image")
        return Response(
            data,
            media_type=result["ContentType"],
            headers={
                "Cache-Control": "private, max-age=3600",
                "X-Content-Type-Options": "nosniff",
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
            raise HTTPException(404, "Image not found") from None
        raise HTTPException(503, "Media storage unavailable") from None
    except BotoCoreError:
        raise HTTPException(503, "Media storage unavailable") from None
