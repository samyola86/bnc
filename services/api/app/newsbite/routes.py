import base64
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth.editor import require_editor, story_access
from app.db.session import get_session
from app.editorial.models import Story
from app.media.routes import MAX_BYTES

from .renderer import definitions
from .schema import NewsBite
from .service import render_content

router = APIRouter(dependencies=[Depends(require_editor)], tags=["news bite"])


class Preview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    news_bite: NewsBite
    cover_image_id: uuid.UUID | None = None
    category: str = Field(default="", max_length=100)
    image_caption: str = Field(default="", max_length=2000)


@router.get("/news-bite/templates")
def templates():
    return {"items": definitions()}


@router.post("/stories/{story_id}/news-bite/preview")
def preview(story_id: uuid.UUID, body: Preview, session: Annotated[Session, Depends(get_session)]):
    story_access(session, session.get(Story, story_id), write=True)
    png, result = render_content(body.model_dump(mode="json"))
    if len(png) > MAX_BYTES:
        result = {
            **result,
            "errors": [*result["errors"], "Rendered graphic exceeds the media size limit"],
        }
    return {**result, "png": base64.b64encode(png).decode()}
