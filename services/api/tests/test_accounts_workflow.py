import uuid
from datetime import timedelta

import pyotp
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import routes
from app.auth.models import LoginSession, ResetToken, User
from app.auth.security import cipher, digest, now
from app.config import get_settings
from app.main import app
from tests.test_ai_stories import save_payload
from tests.test_ingestion import newsroom  # noqa: F401

PASSWORD = "test-only-password"
ORIGIN = {"Origin": "http://localhost:3000"}


@pytest.fixture
def accounts(newsroom, monkeypatch):  # noqa: F811
    admin, factory, _ = newsroom
    monkeypatch.setattr(get_settings(), "auth_encryption_key", Fernet.generate_key().decode())
    users = {}
    clients = {}
    for username, role in (
        ("writer", "CONTENT_WRITER"),
        ("other", "CONTENT_WRITER"),
        ("editor", "EDITOR"),
    ):
        response = admin.post(
            "/api/v1/admin/users",
            json={
                "name": username.title(),
                "email": f"{username}@example.test",
                "username": username,
                "role": role,
                "password": PASSWORD,
            },
        )
        assert response.status_code == 201, response.text
        users[username] = response.json()
        client = TestClient(app, headers=ORIGIN)
        response = client.post(
            "/api/v1/auth/login", json={"identity": username, "password": PASSWORD}
        )
        assert response.status_code == 200, response.text
        clients[username] = client
    yield admin, factory, users, clients
    for client in clients.values():
        client.close()


def create_story(client, **extra):
    response = client.post(
        "/api/v1/stories",
        json={
            "title": "Original report",
            "body": "Verified reporting",
            "category": "World",
            "tags": ["News"],
            "contributors": ["Reporter"],
            "destinations": ["wordpress"],
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def submit(client, draft):
    response = client.post(
        f"/api/v1/stories/{draft['id']}/submit-review", json={"base_version": draft["version"]}
    )
    assert response.status_code == 201, response.text
    return response.json()


def decision(client, draft, request, action, **extra):
    return client.post(
        f"/api/v1/stories/{draft['id']}/{action}",
        json={
            "request_id": request["id"],
            "base_version": draft["version"],
            **extra,
        },
    )


def test_login_logout_expiry_csrf_and_legacy_token(accounts):
    _, factory, _, clients = accounts
    writer = clients["writer"]
    assert writer.get("/api/v1/auth/me").json()["user"]["role"] == "CONTENT_WRITER"
    assert (
        writer.post("/api/v1/auth/logout", headers={"Origin": "https://evil.example"}).status_code
        == 403
    )
    assert writer.post("/api/v1/auth/logout").status_code == 200
    assert writer.get("/api/v1/auth/me").status_code == 401
    assert (
        writer.post(
            "/api/v1/auth/login", json={"identity": "writer", "password": "wrong"}
        ).status_code
        == 401
    )
    response = writer.post(
        "/api/v1/auth/login", json={"identity": "writer@example.test", "password": PASSWORD}
    )
    assert (
        "HttpOnly" in response.headers["set-cookie"]
        and "SameSite=strict" in response.headers["set-cookie"]
    )
    token = writer.cookies.get("bnc_session")
    assert writer.post("/api/v1/auth/renew").status_code == 200
    assert token != writer.cookies.get("bnc_session")
    with factory() as db:
        login = db.scalar(
            select(LoginSession).where(
                LoginSession.token_hash == digest(writer.cookies.get("bnc_session"))
            )
        )
        login.expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert writer.get("/api/v1/auth/me").status_code == 401
    anonymous = TestClient(app, headers=ORIGIN)
    assert (
        anonymous.get(
            "/api/v1/sources", headers={"Authorization": "Bearer test-editor-token"}
        ).status_code
        == 401
    )


def test_rate_limit_and_mfa(accounts):
    _, factory, _, _ = accounts
    client = TestClient(app, headers=ORIGIN)
    response = client.post("/api/v1/auth/login", json={"identity": "admin", "password": PASSWORD})
    assert response.json()["mfa_required"]
    assert client.get("/api/v1/admin/users").status_code == 403
    response = client.post("/api/v1/auth/mfa/setup")
    assert response.status_code == 200
    totp = pyotp.parse_uri(response.json()["uri"])
    response = client.post("/api/v1/auth/mfa/verify", json={"code": totp.now()})
    assert response.status_code == 200, response.text
    assert client.get("/api/v1/admin/users").status_code == 200
    assert client.post("/api/v1/auth/mfa/verify", json={"code": totp.now()}).status_code == 401
    for _ in range(10):
        response = client.post(
            "/api/v1/auth/login", json={"identity": "nonexistent", "password": "wrong"}
        )
        assert response.status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login", json={"identity": "nonexistent", "password": "wrong"}
        ).status_code
        == 429
    )
    with factory() as db:
        admin = db.scalar(select(User).where(User.username == "admin"))
        assert admin.mfa_secret != totp.secret
        assert cipher().decrypt(admin.mfa_secret.encode()).decode() == totp.secret


def test_admin_permissions_revocation_and_last_admin(accounts):
    admin, _, users, clients = accounts
    for name in ("writer", "editor"):
        assert clients[name].get("/api/v1/admin/users").status_code == 403
        assert clients[name].get("/api/v1/admin/system-status").status_code == 403
        assert (
            clients[name]
            .patch("/api/v1/ingestion/settings", json={"automatic_collection": False})
            .status_code
            == 403
        )
    historical = create_story(clients["writer"])
    writer_id = users["writer"]["id"]
    assert (
        admin.post(
            f"/api/v1/admin/users/{writer_id}/status", json={"status": "suspended"}
        ).status_code
        == 200
    )
    assert clients["writer"].get("/api/v1/auth/me").status_code == 401
    admin.post(f"/api/v1/admin/users/{writer_id}/status", json={"status": "active"})
    clients["writer"].post("/api/v1/auth/login", json={"identity": "writer", "password": PASSWORD})
    data = {key: users["writer"][key] for key in ("name", "email", "username", "role")}
    assert (
        admin.patch(f"/api/v1/admin/users/{writer_id}", json={**data, "role": "EDITOR"}).status_code
        == 200
    )
    assert clients["writer"].get("/api/v1/auth/me").status_code == 401
    assert (
        admin.post(
            f"/api/v1/admin/users/{writer_id}/status", json={"status": "deleted"}
        ).status_code
        == 200
    )
    assert (
        clients["writer"]
        .post("/api/v1/auth/login", json={"identity": "writer", "password": PASSWORD})
        .status_code
        == 401
    )
    own = admin.get("/api/v1/auth/me").json()["user"]
    assert (
        admin.post(
            f"/api/v1/admin/users/{own['id']}/status", json={"status": "suspended"}
        ).status_code
        == 409
    )
    payload = {key: own[key] for key in ("name", "email", "username", "role")}
    assert (
        admin.patch(
            f"/api/v1/admin/users/{own['id']}", json={**payload, "role": "EDITOR"}
        ).status_code
        == 409
    )
    assert admin.get("/api/v1/admin/audit").json()["items"]
    retained = clients["editor"].get(f"/api/v1/stories/{historical['id']}").json()
    assert retained["assigned_author"]["id"] == writer_id
    assert retained["assigned_author"]["name"] == "Writer"


def test_reset_is_single_use_revokes_sessions_and_logout_all(accounts, monkeypatch):
    admin, factory, users, clients = accounts
    sent = []
    monkeypatch.setattr(routes, "send_reset", lambda user, token: sent.append(token))
    writer = clients["writer"]
    assert (
        admin.post(f"/api/v1/admin/users/{users['writer']['id']}/reset-password").status_code == 200
    )
    assert writer.get("/api/v1/auth/me").status_code == 401
    payload = {"token": sent[0], "password": "new-test-password"}
    assert writer.post("/api/v1/auth/reset-password", json=payload).status_code == 200
    assert writer.post("/api/v1/auth/reset-password", json=payload).status_code == 422
    assert (
        writer.post(
            "/api/v1/auth/login", json={"identity": "writer", "password": "new-test-password"}
        ).status_code
        == 200
    )
    assert writer.post("/api/v1/auth/logout-all").status_code == 200
    assert writer.get("/api/v1/auth/me").status_code == 401
    with factory() as db:
        token = db.scalar(select(ResetToken))
        assert token.used and token.token_hash != sent[0]


def test_writer_editor_workflow_access_and_immutable_approval(accounts):
    admin, _, users, clients = accounts
    writer, editor, other = clients["writer"], clients["editor"], clients["other"]
    draft = create_story(writer)
    task = admin.post(
        "/api/v1/tasks",
        json={
            "title": "Prepare verified report",
            "assignee_id": users["writer"]["id"],
            "story_id": draft["id"],
        },
    ).json()
    assert (
        writer.post(
            f"/api/v1/tasks/{task['id']}/status", json={"status": "IN_PROGRESS"}
        ).status_code
        == 200
    )
    assert (
        writer.post(f"/api/v1/tasks/{task['id']}/status", json={"status": "IN_REVIEW"}).status_code
        == 200
    )
    path = f"/api/v1/stories/{draft['id']}"
    assert other.get(path).status_code == 403
    assert other.patch(path, json=save_payload(draft)).status_code == 403
    assert other.get(path + "/versions").status_code == 403
    assert other.get("/api/v1/stories?origin=all").json()["total"] == 0
    request = submit(writer, draft)
    assert submit(writer, draft)["id"] == request["id"]
    assert writer.patch(path, json=save_payload(draft)).status_code == 409
    assert decision(writer, draft, request, "approve").status_code == 403
    assert decision(editor, draft, request, "request-changes").status_code == 422
    assert (
        decision(editor, draft, request, "request-changes", notes="Verify the date").status_code
        == 200
    )
    payload = save_payload(draft, body="Verified date", category="World", tags=["News"])
    draft = writer.patch(path, json=payload).json()
    request = submit(writer, draft)
    assert decision(editor, draft, request, "approve").status_code == 200
    completed = writer.get("/api/v1/tasks").json()["items"][0]
    assert completed["status"] == "COMPLETED" and completed["completed_at"]
    assert decision(editor, draft, request, "ready").status_code == 200
    assert writer.get(path).json()["status"] == "READY"
    detail = editor.get(f"/api/v1/publishing/requests/{request['id']}").json()
    assert detail["draft"]["version"] == 2
    assert detail["request"]["reviewer"] == "Editor"
    assert "APPROVED" in [event["decision"] for event in detail["history"]]
    changed = writer.patch(path, json=save_payload(draft, title="New headline")).json()
    assert changed["version"] == 3 and changed["status"] == "DRAFT"
    assert decision(editor, changed, request, "ready").status_code == 409
    assert other.get(f"/api/v1/publishing/requests/{request['id']}").status_code == 403


def test_self_approval_rejection_withdrawal_and_readiness(accounts):
    admin, _, _, clients = accounts
    editor, writer = clients["editor"], clients["writer"]
    draft = create_story(editor)
    request = submit(editor, draft)
    assert decision(editor, draft, request, "approve").status_code == 403
    assert (
        decision(admin, draft, request, "reject", notes="Needs independent evidence").status_code
        == 200
    )
    assert admin.get(f"/api/v1/publishing/requests/{request['id']}").json()["request"][
        "review_notes"
    ]
    own = create_story(admin)
    request = submit(admin, own)
    assert decision(admin, own, request, "approve").status_code == 403
    assert (
        decision(
            admin,
            own,
            request,
            "approve",
            self_approval_override=True,
            notes="Urgent administrative exception",
        ).status_code
        == 200
    )
    draft = create_story(writer, body="", tags=[], contributors=[], destinations=["instagram"])
    response = writer.post(f"/api/v1/stories/{draft['id']}/submit-review", json={"base_version": 1})
    assert response.status_code == 422
    assert {"body", "tags", "contributors", "cover_image_id"} <= set(
        response.json()["error"]["fields"]
    )
    draft = create_story(writer)
    assert draft["warnings"] == ["Missing source credit"]
    request = submit(writer, draft)
    assert writer.post(f"/api/v1/publishing/queue/{request['id']}/cancel").status_code == 200
    history = writer.get(f"/api/v1/publishing/requests/{request['id']}").json()["history"]
    assert history[-1]["decision"] == "WITHDRAWN"


def test_assignment_reassignment_and_task_history(accounts):
    admin, _, users, clients = accounts
    draft = create_story(admin)
    payload = {
        "title": "Report the story",
        "assignee_id": users["writer"]["id"],
        "story_id": draft["id"],
        "priority": "HIGH",
    }
    response = admin.post("/api/v1/tasks", json=payload)
    assert response.status_code == 201, response.text
    task = response.json()
    writer, other = clients["writer"], clients["other"]
    assert writer.get("/api/v1/tasks").json()["items"][0]["id"] == task["id"]
    assert writer.get(f"/api/v1/stories/{draft['id']}").status_code == 200
    assert (
        other.post(f"/api/v1/tasks/{task['id']}/status", json={"status": "IN_PROGRESS"}).status_code
        == 403
    )
    assert (
        writer.post(
            f"/api/v1/tasks/{task['id']}/status", json={"status": "IN_PROGRESS"}
        ).status_code
        == 200
    )
    assert (
        writer.post(f"/api/v1/tasks/{task['id']}/status", json={"status": "COMPLETED"}).status_code
        == 409
    )
    assert (
        admin.patch(
            f"/api/v1/tasks/{task['id']}", json={**payload, "assignee_id": users["other"]["id"]}
        ).status_code
        == 200
    )
    assert writer.get(f"/api/v1/stories/{draft['id']}").status_code == 403
    assert len(other.get(f"/api/v1/tasks/{task['id']}/history").json()["items"]) >= 3
    assert other.post("/api/v1/tasks", json=payload).status_code == 403


def test_one_time_bootstrap_no_legacy_elevation(accounts):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.auth.bootstrap import bootstrap
    from app.auth.routes import Account
    from app.db.base import Base

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        legacy = User(
            name="Legacy", email="legacy@example.test", role="CONTENT_WRITER", active=False
        )
        db.add(legacy)
        db.commit()
        account = Account(
            name="Owner", email="owner@example.test", username="owner", role="SUPERADMIN"
        )
        bootstrap(db, account, PASSWORD)
        assert db.get(User, legacy.id).role == "CONTENT_WRITER"
        assert not db.get(User, legacy.id).active
        with pytest.raises(ValueError, match="Bootstrap is closed"):
            bootstrap(db, account, PASSWORD)
    engine.dispose()


def test_suspended_account_cannot_execute_pending_ai_job(accounts, monkeypatch):
    from app.ai import tasks
    from app.ai.models import AIJob
    from app.api.v1 import stories

    admin, factory, users, clients = accounts
    monkeypatch.setattr(get_settings(), "openai_api_key", "test-key-only")
    monkeypatch.setattr(get_settings(), "openai_model", "test-model")
    monkeypatch.setattr(stories, "enqueue", lambda _: True)
    monkeypatch.setattr(
        tasks, "generate", lambda *_: pytest.fail("Suspended user must not incur AI calls")
    )
    draft = create_story(clients["writer"])
    response = clients["writer"].post(
        f"/api/v1/stories/{draft['id']}/ai-draft",
        json={
            "base_version": 1,
            "language": "en",
            "reporting_notes": "Original verified observations",
            "notes_permitted": True,
        },
    )
    assert response.status_code == 202, response.text
    admin.post(f"/api/v1/admin/users/{users['writer']['id']}/status", json={"status": "suspended"})
    job_id = uuid.UUID(response.json()["job_id"])
    tasks.run_job(job_id, factory)
    with factory() as session:
        assert session.get(AIJob, job_id).status == "FAILED"
