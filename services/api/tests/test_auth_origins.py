import pyotp
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.main import app
from tests.test_accounts_workflow import PASSWORD, accounts, create_story  # noqa: F401
from tests.test_ingestion import newsroom  # noqa: F401

PUBLIC = "https://trustable-detail-drift.ngrok-free.dev"


@pytest.mark.parametrize("origin", ["http://localhost:3000", PUBLIC])
@pytest.mark.parametrize("identity", ["writer", "admin"])
def test_origin_login_mfa_renew_and_logout(accounts, monkeypatch, origin, identity):  # noqa: F811
    _, _, _, _ = accounts
    monkeypatch.setattr(get_settings(), "auth_additional_origins", [PUBLIC])
    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        response = client.post(
            "/api/v1/auth/login", json={"identity": identity, "password": PASSWORD}
        )
        assert response.status_code == 200, response.text
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie
        assert "Domain=" not in cookie
        assert ("Secure" in cookie) == origin.startswith("https:")
        assert client.get("/api/v1/auth/me").status_code == 200
        if identity == "admin":
            assert response.json()["mfa_required"]
            assert client.get("/api/v1/stories").status_code == 403
        response = client.post("/api/v1/auth/mfa/setup")
        assert response.status_code == 200
        totp = pyotp.parse_uri(response.json()["uri"])
        response = client.post("/api/v1/auth/mfa/verify", json={"code": totp.now()})
        assert response.status_code == 200, response.text
        assert ("Secure" in response.headers["set-cookie"]) == origin.startswith("https:")
        assert create_story(client)["id"]
        other = PUBLIC if origin.startswith("http://") else "http://localhost:3000"
        assert client.get(other + "/api/v1/auth/me").status_code == 401
        response = client.post("/api/v1/auth/renew")
        assert response.status_code == 200
        assert ("Secure" in response.headers["set-cookie"]) == origin.startswith("https:")
        response = client.post("/api/v1/auth/logout")
        assert response.status_code == 200
        assert "HttpOnly" in response.headers["set-cookie"]
        assert ("Secure" in response.headers["set-cookie"]) == origin.startswith("https:")
        assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize(
    "origin",
    [
        "null",
        "https://evil.example",
        PUBLIC + ".evil.example",
        "http://trustable-detail-drift.ngrok-free.dev",
        PUBLIC + "/",
    ],
)
def test_untrusted_origins_and_forwarding_headers_rejected(accounts, monkeypatch, origin):  # noqa: F811
    admin, _, _, _ = accounts
    monkeypatch.setattr(get_settings(), "auth_additional_origins", [PUBLIC])
    headers = {"Origin": origin, "X-Forwarded-Host": PUBLIC[8:], "X-Forwarded-Proto": "https"}
    assert admin.post("/api/v1/auth/renew", headers=headers).status_code == 403
    assert (
        admin.post(
            "/api/v1/auth/login", headers=headers, json={"identity": "writer", "password": PASSWORD}
        ).status_code
        == 403
    )


def test_cross_site_and_secure_policy_preserved(accounts, monkeypatch):  # noqa: F811
    admin, _, _, _ = accounts
    assert (
        admin.post("/api/v1/auth/renew", headers={"Sec-Fetch-Site": "cross-site"}).status_code
        == 403
    )
    monkeypatch.setattr(get_settings(), "auth_cookie_secure", True)
    response = admin.post("/api/v1/auth/login", json={"identity": "writer", "password": PASSWORD})
    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://*.ngrok-free.dev",
        "https://site.test/path",
        "https://user:pass@site.test",
        "http://site.test",
        "null",
    ],
)
def test_origin_configuration_is_strict(origin):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, auth_additional_origins=[origin])
