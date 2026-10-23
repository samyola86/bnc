from datetime import date

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.session import get_session
from app.main import app
from app.newsbite.schema import NewsBite
from tests.auth_helpers import session_cookie
from tests.test_ai_stories import save_payload
from tests.test_ingestion_postgres import postgres  # noqa: F401


def test_news_bite_json_round_trip_and_immutable_history(postgres, monkeypatch):  # noqa: F811
    def database():
        with postgres() as session:
            yield session

    monkeypatch.setattr(get_settings(), "auth_cookie_secure", False)
    app.dependency_overrides[get_session] = database
    try:
        with TestClient(
            app, cookies=session_cookie(postgres), headers={"Origin": "http://localhost:3000"}
        ) as client:
            config = NewsBite(
                template_version=2,
                layout_version=2,
                headline="বাংলাদেশের নাগরিকদের জন্য নির্ভরযোগ্য সংবাদ",
                highlight="নির্ভরযোগ্য সংবাদ",
                publication_date=date(2026, 10, 22),
            ).model_dump(mode="json")
            response = client.post(
                "/api/v1/stories",
                json={"title": "Bengali graphic", "format": "news_bite", "news_bite": config},
            )
            assert response.status_code == 201, response.text
            draft = response.json()
            path = "/api/v1/stories/" + draft["id"]
            assert client.get(path).json()["news_bite"] == config
            next_config = {**config, "template_id": "dark-editorial", "focal_y": 0.2}
            saved = client.patch(
                path, json=save_payload(draft, news_bite=next_config, format="news_bite")
            ).json()
            assert saved["news_bite"] == next_config
            assert client.patch(path, json=save_payload(draft, news_bite=config)).status_code == 409
            versions = client.get(path + "/versions").json()["items"]
            assert versions[0]["content"]["news_bite"] == next_config
            assert versions[1]["content"]["news_bite"] == config
            assert client.post(path + "/submit-review", json={"base_version": 2}).status_code == 422
    finally:
        app.dependency_overrides.clear()
