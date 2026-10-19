import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.editor import current_user, ensure_editor, require_editor
from app.auth.models import User
from app.db.session import get_session
from app.editorial.models import AuditEvent, Story
from app.ingestion.service import audit, now
from app.tasks.models import NewsroomTask

router = APIRouter(prefix="/tasks", dependencies=[Depends(require_editor)], tags=["newsroom tasks"])
DB = Annotated[Session, Depends(get_session)]


class TaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    assignee_id: uuid.UUID
    story_id: uuid.UUID | None = None
    priority: Literal["LOW", "MEDIUM", "HIGH", "URGENT"] = "MEDIUM"
    due_at: datetime | None = None
    feedback: str = Field(default="", max_length=5000)

    @field_validator("due_at")
    @classmethod
    def timezone(cls, value):
        if value and value.utcoffset() is None:
            raise ValueError("Due date must include a timezone")
        return value

    @field_validator("title")
    @classmethod
    def title_required(cls, value):
        if not value.strip():
            raise ValueError("Task title is required")
        return value.strip()


def admin_only(session):
    if current_user(session).role != "SUPERADMIN":
        raise HTTPException(403, "Only Superadmins can assign or reassign tasks")


def validate_assignment(session, body):
    user = session.get(User, body.assignee_id)
    if (
        not user
        or not user.active
        or user.deleted_at
        or user.role not in {"EDITOR", "CONTENT_WRITER"}
    ):
        raise HTTPException(422, "Assign an active Editor or Content Writer")
    if body.story_id and not session.get(Story, body.story_id):
        raise HTTPException(422, "Related story not found")


def view(session, task):
    user = session.get(User, task.assignee_id)
    story = session.get(Story, task.story_id) if task.story_id else None
    return {
        **{
            key: getattr(task, key)
            for key in (
                "id",
                "title",
                "description",
                "assignee_id",
                "creator_id",
                "story_id",
                "priority",
                "status",
                "due_at",
                "created_at",
                "updated_at",
                "completed_at",
                "feedback",
            )
        },
        "assignee_name": user.name,
        "story_origin_item_id": story.origin_item_id if story else None,
    }


def get_task(session, task_id):
    task = session.scalar(select(NewsroomTask).where(NewsroomTask.id == task_id).with_for_update())
    if not task:
        raise HTTPException(404, "Task not found")
    if current_user(session).role != "SUPERADMIN" and task.assignee_id != ensure_editor(session):
        raise HTTPException(403, "This task is not assigned to you")
    return task


@router.get("")
def list_tasks(session: DB, all_tasks: bool = False):
    statement = select(NewsroomTask).order_by(NewsroomTask.created_at.desc()).limit(200)
    if not all_tasks or current_user(session).role != "SUPERADMIN":
        statement = statement.where(NewsroomTask.assignee_id == ensure_editor(session))
    return {"items": [view(session, task) for task in session.scalars(statement)]}


@router.post("", status_code=201)
def create(body: TaskInput, session: DB):
    admin_only(session)
    validate_assignment(session, body)
    task = NewsroomTask(**body.model_dump(), creator_id=ensure_editor(session))
    session.add(task)
    session.flush()
    audit(
        session, "task.created", task.id, ensure_editor(session), assignee_id=str(task.assignee_id)
    )
    session.commit()
    return view(session, task)


@router.patch("/{task_id}")
def edit(task_id: uuid.UUID, body: TaskInput, session: DB):
    admin_only(session)
    validate_assignment(session, body)
    task = get_task(session, task_id)
    previous = task.assignee_id
    for key, value in body.model_dump().items():
        setattr(task, key, value)
    audit(
        session,
        "task.updated",
        task.id,
        ensure_editor(session),
        previous_assignee_id=str(previous),
        assignee_id=str(task.assignee_id),
        feedback=task.feedback,
    )
    session.commit()
    return view(session, task)


class TaskStatus(BaseModel):
    status: Literal["TO_DO", "IN_PROGRESS", "IN_REVIEW", "COMPLETED"]


@router.post("/{task_id}/status")
def status(task_id: uuid.UUID, body: TaskStatus, session: DB):
    task = get_task(session, task_id)
    if current_user(session).role != "SUPERADMIN":
        transitions = {
            "TO_DO": {"IN_PROGRESS"},
            "IN_PROGRESS": {"IN_REVIEW", "COMPLETED"},
            "IN_REVIEW": {"IN_PROGRESS", "COMPLETED"},
            "COMPLETED": set(),
        }
        if body.status != task.status and body.status not in transitions[task.status]:
            raise HTTPException(409, "Only Superadmins can reopen tasks or skip workflow stages")
        if body.status == "COMPLETED" and task.story_id:
            story = session.get(Story, task.story_id)
            if story.status not in {"APPROVED", "READY"}:
                raise HTTPException(
                    409, "Story-linked tasks require editorial approval to complete"
                )
    task.status = body.status
    task.completed_at = now() if task.status == "COMPLETED" else None
    audit(session, "task.status_changed", task.id, ensure_editor(session), status=task.status)
    session.commit()
    return view(session, task)


@router.get("/{task_id}/history")
def history(task_id: uuid.UUID, session: DB):
    get_task(session, task_id)
    rows = session.scalars(
        select(AuditEvent).where(AuditEvent.resource_id == task_id).order_by(AuditEvent.created_at)
    )
    return {
        "items": [
            {
                "action": row.action,
                "actor_id": row.actor_id,
                "created_at": row.created_at,
                "details": row.event_details,
            }
            for row in rows
        ]
    }
