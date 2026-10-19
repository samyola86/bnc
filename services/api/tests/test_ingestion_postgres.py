"""Run with BNC_TEST_DATABASE_URL to verify real PostgreSQL locks/uniqueness.

Each test uses an isolated random schema, never the editorial tables.
"""

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from app.auth.editor import EDITOR_ID
from app.db.base import Base
from app.editorial.drafts import create_draft, update_draft
from app.editorial.models import Story, StoryVersion
from app.ingestion.candidates import list_candidates
from app.ingestion.models import CollectionRun, FeedEntry, IngestedItem, Source
from app.ingestion.schemas import DraftInput
from app.ingestion.service import collect_run, now
from app.ingestion.tasks import reserve_due
from tests.auth_helpers import seed_actor
from tests.test_ingestion import rss


@pytest.fixture
def postgres():
    url = os.environ.get("BNC_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set BNC_TEST_DATABASE_URL for isolated PostgreSQL integration checks")
    admin = create_engine(url, connect_args={"connect_timeout": 10})
    schema = "bnc_rss_test_" + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(CreateSchema(schema))
    engine = create_engine(
        url, connect_args={"options": f"-csearch_path={schema}", "connect_timeout": 10}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, info={"actor_id": EDITOR_ID})
    with factory() as identity_session:
        seed_actor(identity_session)
        identity_session.commit()
    try:
        yield factory
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()


def test_concurrent_collections_preserve_one_candidate_and_all_attributions(postgres):
    factory = postgres
    with factory() as session:
        ids = []
        for name in ["One", "Two"]:
            source = Source(
                publisher=name,
                homepage="https://publisher.example/",
                url="https://publisher.example/feed",
            )
            session.add(source)
            session.flush()
            run = CollectionRun(source_id=source.id)
            session.add(run)
            session.flush()
            ids.append(run.id)
        session.commit()
    barrier = threading.Barrier(2)

    class FeedServer:
        def fetch(self, *args):
            barrier.wait(timeout=15)
            return rss()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda run_id: collect_run(run_id, factory, FeedServer), ids))
    assert all(result["status"] == "SUCCEEDED" for result in results), results
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(IngestedItem)) == 1
        assert session.scalar(select(func.count()).select_from(FeedEntry)) == 2
        page = list_candidates(session)
        assert page["total"] == 1 and len(page["items"][0]["attributions"]) == 2
        item_id = session.scalar(select(IngestedItem.id))
        seed_actor(session)
        session.commit()

    def draft():
        with factory() as session:
            seed_actor(session)
            return create_draft(session, item_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        drafts = list(pool.map(lambda _: draft(), [1, 2]))
    assert drafts[0]["id"] == drafts[1]["id"]

    def edit():
        with factory() as session:
            seed_actor(session)
            try:
                update_draft(
                    session,
                    uuid.UUID(drafts[0]["id"]),
                    DraftInput(base_version=1, title="Original BNC story", credits=[]),
                )
                return 200
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: edit(), [1, 2]))
    assert sorted(outcomes) == [200, 409]
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Story)) == 1
        assert session.scalar(select(func.count()).select_from(StoryVersion)) == 2
        run = CollectionRun(source_id=session.get(CollectionRun, ids[0]).source_id)
        session.add(run)
        session.commit()
        run_id = run.id

    class ExpandedFeed:
        def fetch(self, *args):
            return rss(45)

    assert collect_run(run_id, factory, ExpandedFeed)["inserted"] == 44
    with factory() as session:
        first = list_candidates(session, status="all")
        second = list_candidates(session, status="all", cursor=first["next_cursor"])
        assert len(first["items"]) == 30 and len(second["items"]) == 15
        assert not (
            {item["id"] for item in first["items"]} & {item["id"] for item in second["items"]}
        )


def test_parallel_scheduler_ticks_reserve_a_source_once(postgres):
    factory = postgres
    with factory() as session:
        source = Source(
            publisher="Due",
            homepage="https://publisher.example/",
            url="https://publisher.example/feed",
            next_collection_at=now() - timedelta(minutes=1),
        )
        session.add(source)
        session.commit()

    def reserve():
        with factory() as session:
            seed_actor(session)
            return reserve_due(session)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: reserve(), [1, 2]))
    assert sum(map(len, results)) == 1
