"""PostgreSQL persistence/concurrency for the shared manual and AI editing workflow."""

import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.ai import tasks
from app.ai.models import AIJob
from app.ai.schemas import GenerateInput
from app.ai.service import request_job
from app.auth.editor import ensure_editor
from app.config import get_settings
from app.db.session import get_session
from app.editorial.drafts import draft_view, update_draft
from app.editorial.models import StoryVersion
from app.ingestion.schemas import DraftInput
from app.main import app
from tests.test_ai_stories import generated, save_payload
from tests.test_ingestion_postgres import postgres  # noqa: F401


def test_manual_ai_persistence_and_parallel_revision_saves(postgres, monkeypatch):  # noqa: F811
    factory = postgres

    def database():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = database
    monkeypatch.setattr(get_settings(), "ingestion_api_token", "test-editor-token")
    monkeypatch.setattr(get_settings(), "openai_api_key", "test-not-a-real-key")
    monkeypatch.setattr(get_settings(), "openai_model", "test-model")
    try:
        with TestClient(app, headers={"Authorization": "Bearer test-editor-token"}) as client:
            response = client.post(
                "/api/v1/stories", json={"title": "Independent report", "body": "Editor writing"}
            )
            assert response.status_code == 201
            draft = response.json()
            story_id = uuid.UUID(draft["id"])
            with factory() as session:
                job = request_job(
                    session,
                    story_id,
                    GenerateInput(
                        base_version=1,
                        language="bn",
                        reporting_notes="River observed",
                        notes_permitted=True,
                    ),
                )
                job_id = job.id
            monkeypatch.setattr(tasks, "generate", lambda *_: (generated(), {"total_tokens": 150}))
            tasks.run_job(job_id, factory)
            with factory() as session:
                job = session.get(AIJob, job_id)
                assert job.status == "SUCCEEDED" and job.usage["total_tokens"] == 150
                assert draft_view(session, story_id)["body"] == "Editor writing"
            response = client.patch(
                f"/api/v1/stories/{story_id}",
                json=save_payload(draft, body="AI preview with human edits", ai_job_id=str(job_id)),
            )
            assert response.status_code == 200, response.text
            saved = response.json()
            assert saved["version"] == 2 and saved["human_review_required"]
            assert saved["warnings"] == ["Missing source credit"]

            def edit(_):
                with factory() as session:
                    try:
                        update_draft(
                            session, story_id, DraftInput(base_version=2, title="Concurrent edit")
                        )
                        return 200
                    except HTTPException as exc:
                        return exc.status_code

            with ThreadPoolExecutor(max_workers=2) as pool:
                assert sorted(pool.map(edit, [1, 2])) == [200, 409]
            with factory() as session:
                assert session.scalar(select(func.count()).select_from(StoryVersion)) == 3
    finally:
        app.dependency_overrides.clear()


def test_parallel_ai_requests_reserve_one_job(postgres, monkeypatch):  # noqa: F811
    from app.api.v1.stories import ManualInput, create_story

    factory = postgres
    monkeypatch.setattr(get_settings(), "openai_api_key", "test-not-a-real-key")
    monkeypatch.setattr(get_settings(), "openai_model", "test-model")
    with factory() as session:
        ensure_editor(session)
        session.commit()
        story = create_story(ManualInput(title="Parallel AI"), session)

    def generate(_):
        with factory() as session:
            try:
                request_job(
                    session,
                    uuid.UUID(story["id"]),
                    GenerateInput(
                        base_version=1,
                        language="bn",
                        reporting_notes="Observation",
                        notes_permitted=True,
                    ),
                )
                return 202
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(generate, [1, 2])) == [202, 409]
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AIJob)) == 1
