from sqlalchemy import create_engine, inspect

from app.db import models  # noqa: F401
from app.db.base import Base


def test_foundation_schema_is_resolvable():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == {
        "users",
        "sources",
        "stories",
        "story_versions",
        "channels",
        "publications",
    }
    constraints = inspector.get_unique_constraints("story_versions")
    assert any(c["column_names"] == ["story_id", "version_number"] for c in constraints)


def test_initial_migration_matches_models_and_downgrades(tmp_path, monkeypatch):
    from pathlib import Path

    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext

    from alembic import command
    from app.config import get_settings

    api_root = Path(__file__).resolve().parents[1]
    database_url = f"sqlite:///{(tmp_path / 'migration.db').as_posix()}"
    monkeypatch.setattr(get_settings(), "database_url", database_url)
    config = Config(str(api_root / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    engine.dispose()
    command.downgrade(config, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]


def test_dashboard_counts_database_records():
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from app.db.session import get_session
    from app.editorial.models import Story
    from app.main import app

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([Story(status="DRAFT"), Story(status="IN_REVIEW")])
        session.commit()

    def test_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    try:
        response = TestClient(app).get("/api/v1/dashboard/overview")
        assert response.status_code == 200
        assert response.json() == {
            "stories": 2,
            "in_review": 1,
            "approved": 0,
            "publications_pending": 0,
        }
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
