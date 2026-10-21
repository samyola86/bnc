from sqlalchemy import create_engine, inspect

from app.db import models  # noqa: F401
from app.db.base import Base


def test_foundation_schema_is_resolvable():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == {
        "intelligence_settings",
        "item_analyses",
        "story_clusters",
        "cluster_members",
        "trend_snapshots",
        "intelligence_usage",
        "provider_observations",
        "users",
        "sources",
        "stories",
        "story_versions",
        "channels",
        "publications",
        "publishing_requests",
        "login_sessions",
        "password_reset_tokens",
        "auth_attempts",
        "newsroom_tasks",
        "review_decisions",
        "feeds",
        "feed_entries",
        "ingested_items",
        "collection_runs",
        "ingestion_settings",
        "story_sources",
        "audit_events",
        "ai_jobs",
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
    # Verify an existing registry record survives the additive migration safely.
    command.upgrade(config, "0001_foundation")
    from sqlalchemy import text

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO sources (id,publisher,homepage,language,rights,notes) "
                "VALUES ('00000000000000000000000000000001','Existing publisher',"
                "'https://publisher.example/','en','unverified',NULL)"
            )
        )
    engine.dispose()
    command.upgrade(config, "a81b6d2c930f")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("UPDATE sources SET polling_interval=47"))
        connection.execute(text("UPDATE ingestion_settings SET candidate_limit=40 WHERE id=1"))
    engine.dispose()
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        row = connection.execute(
            text("SELECT url, active, source_type, extraction_mode, notes FROM sources")
        ).one()
        assert tuple(row) == ("https://publisher.example/", 0, "manual", "reference_only", "")
        assert connection.execute(text("SELECT polling_interval FROM sources")).scalar() == 47
        assert tuple(
            connection.execute(
                text(
                    "SELECT candidate_limit,default_interval,draft_language,source_mode,"
                    "preferred_categories,automatic_collection FROM ingestion_settings"
                )
            ).one()
        ) == (40, 15, "bn", "all_supported", "[]", 1)
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
        from sqlalchemy.orm import sessionmaker

        from tests.auth_helpers import session_cookie

        factory = sessionmaker(bind=engine)
        response = TestClient(app, cookies=session_cookie(factory)).get(
            "/api/v1/dashboard/overview"
        )
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


def test_account_migration_preserves_legacy_authorship_and_requests(tmp_path, monkeypatch):
    from pathlib import Path

    from alembic.config import Config
    from sqlalchemy import text

    from alembic import command
    from app.config import get_settings

    database_url = f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}"
    monkeypatch.setattr(get_settings(), "database_url", database_url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "d23a10e93c41")
    engine = create_engine(database_url)
    user_id, story_id, version_id, request_id, audit_id = [f"{n:032x}" for n in range(1, 6)]
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id,email,name,role,active) "
                "VALUES (:id,'legacy@example.test','Legacy','editor',true)"
            ),
            {"id": user_id},
        )
        connection.execute(
            text(
                "INSERT INTO stories (id,type,language,status,author_id) "
                "VALUES (:id,'article','en','DRAFT',:user)"
            ),
            {"id": story_id, "user": user_id},
        )
        connection.execute(
            text(
                "INSERT INTO story_versions "
                "(id,story_id,version_number,editor_id,title,content_json) "
                "VALUES (:id,:story,1,:user,'Legacy article','{}')"
            ),
            {"id": version_id, "story": story_id, "user": user_id},
        )
        connection.execute(
            text(
                "INSERT INTO publishing_requests (id,story_id,version_id,destinations,status) "
                "VALUES (:id,:story,:version,'[\"wordpress\"]','QUEUED')"
            ),
            {"id": request_id, "story": story_id, "version": version_id},
        )
        connection.execute(
            text(
                "INSERT INTO audit_events (id,actor_id,action,resource_id,event_details) "
                "VALUES (:id,:user,'legacy.created',:story,'{}')"
            ),
            {"id": audit_id, "user": user_id, "story": story_id},
        )
    engine.dispose()
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    with engine.connect() as connection:
        user = connection.execute(
            text("SELECT role,active,password_hash FROM users WHERE id=:id"), {"id": user_id}
        ).one()
        assert tuple(user) == ("CONTENT_WRITER", 0, None)
        assert (
            connection.execute(
                text("SELECT author_id FROM stories WHERE id=:id"), {"id": story_id}
            ).scalar()
            == user_id
        )
        assert (
            connection.execute(
                text("SELECT editor_id FROM story_versions WHERE id=:id"), {"id": version_id}
            ).scalar()
            == user_id
        )
        assert (
            connection.execute(
                text("SELECT status FROM publishing_requests WHERE id=:id"), {"id": request_id}
            ).scalar()
            == "QUEUED"
        )
        assert (
            connection.execute(
                text("SELECT actor_id FROM audit_events WHERE id=:id"), {"id": audit_id}
            ).scalar()
            == user_id
        )
    engine.dispose()
