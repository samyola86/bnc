from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.session import get_session
from app.main import app
from tests.auth_helpers import session_cookie
from tests.test_accounts_workflow import PASSWORD, create_story, decision, submit
from tests.test_ingestion_postgres import postgres  # noqa: F401


def test_concurrent_decisions_only_approve_one_exact_revision(postgres, monkeypatch):  # noqa: F811
    factory = postgres
    monkeypatch.setattr(get_settings(), "auth_cookie_secure", False)

    def database():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = database
    origin = {"Origin": "http://localhost:3000"}
    try:
        admin = TestClient(app, cookies=session_cookie(factory), headers=origin)
        for name, role in (("pgwriter", "CONTENT_WRITER"), ("pgeditor", "EDITOR")):
            response = admin.post(
                "/api/v1/admin/users",
                json={
                    "name": name,
                    "email": f"{name}@example.test",
                    "username": name,
                    "role": role,
                    "password": PASSWORD,
                },
            )
            assert response.status_code == 201, response.text
        writer = TestClient(app, headers=origin)
        editor = TestClient(app, headers=origin)
        for client, name in ((writer, "pgwriter"), (editor, "pgeditor")):
            assert (
                client.post(
                    "/api/v1/auth/login",
                    json={
                        "identity": name,
                        "password": PASSWORD,
                    },
                ).status_code
                == 200
            )
        draft = create_story(writer)
        request = submit(writer, draft)
        cookies = dict(editor.cookies)

        def approve(_):
            with TestClient(app, headers=origin, cookies=cookies) as client:
                return decision(client, draft, request, "approve").status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(approve, (1, 2))) == [200, 409]
        detail = editor.get(f"/api/v1/publishing/requests/{request['id']}").json()
        assert sum(event["decision"] == "APPROVED" for event in detail["history"]) == 1
        assert detail["draft"]["version"] == draft["version"]
    finally:
        app.dependency_overrides.clear()
