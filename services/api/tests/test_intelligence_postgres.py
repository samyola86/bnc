from concurrent.futures import ThreadPoolExecutor

from app.config import get_settings
from app.ingestion.models import IngestedItem
from app.intelligence.classification import controls, fingerprint, reserve
from tests.test_ingestion_postgres import postgres  # noqa: F401
from tests.test_intelligence import seeded


def test_budget_and_concurrency_reservations_serialize(postgres, monkeypatch):  # noqa: F811
    factory = postgres
    first, _ = seeded(factory)
    second, _ = seeded(factory, title="Dhaka transport policy announced today")
    env = get_settings()
    for name, value in {
        "openai_api_key": "test",
        "openai_classification_model": "cheap",
        "openai_classification_input_per_million": 1,
        "openai_classification_output_per_million": 1,
    }.items():
        monkeypatch.setattr(env, name, value)
    with factory() as session:
        row, config = controls(session)
        row.config = {
            **config.model_dump(),
            "model": "cheap",
            "automatic_classification": True,
            "daily_budget_usd": 0.02,
            "concurrency": 4,
        }
        session.commit()

    def attempt(item_id):
        with factory() as session:
            _, config = controls(session)
            item = session.get(IngestedItem, item_id)
            usage = reserve(session, item, config, fingerprint(item, config) + str(item_id))
            accepted = usage is not None
            session.commit()
            return accepted

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, (first, second))) == [False, True]
