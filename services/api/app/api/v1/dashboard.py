from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.editorial.models import Story
from app.publishing.models import Publication

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class Overview(BaseModel):
    stories: int
    in_review: int
    approved: int
    publications_pending: int


@router.get("/overview", response_model=Overview)
def overview(session: Annotated[Session, Depends(get_session)]) -> Overview:
    def story_count(status: str | None = None) -> int:
        query = select(func.count()).select_from(Story)
        if status:
            query = query.where(Story.status == status)
        return session.scalar(query) or 0

    pending = (
        session.scalar(
            select(func.count())
            .select_from(Publication)
            .where(Publication.status.in_(["PENDING", "SCHEDULED", "RUNNING"]))
        )
        or 0
    )
    return Overview(
        stories=story_count(),
        in_review=story_count("IN_REVIEW"),
        approved=story_count("APPROVED"),
        publications_pending=pending,
    )
