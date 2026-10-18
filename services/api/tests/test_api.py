from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_session
from app.main import app

client = TestClient(app)


def test_liveness_and_trace():
    response = client.get("/health/live")
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]


def test_missing_route_uses_error_contract():
    response = client.get("/api/v1/missing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HTTP_404"


def test_database_failure_does_not_expose_connection_details():
    def unavailable():
        raise OperationalError("secret connection string", {}, Exception("private"))

    app.dependency_overrides[get_session] = unavailable
    try:
        response = client.get("/api/v1/dashboard/overview")
        assert response.status_code == 503
        assert "secret" not in response.text
        assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    finally:
        app.dependency_overrides.clear()
