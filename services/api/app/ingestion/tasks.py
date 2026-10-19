import uuid
from datetime import timedelta

from sqlalchemy import select

from app.db import models  # noqa: F401 - workers need the complete FK metadata too
from app.db.session import SessionLocal
from app.ingestion.models import CollectionRun, Source
from app.ingestion.service import audit, collect_run, collectible, next_collection, now
from app.workers.celery_app import celery_app


def enqueue(run_id: uuid.UUID) -> bool:
    try:
        collect_source.apply_async(args=[str(run_id)], task_id=str(run_id), retry=False)
        return True
    except Exception:
        with SessionLocal() as session:
            run = session.get(CollectionRun, run_id)
            if run and run.status == "PENDING":
                run.status, run.message, run.finished_at = (
                    "FAILED",
                    "Queue unavailable; collection will be retried on the next schedule",
                    now(),
                )
                source = session.get(Source, run.source_id)
                source.next_collection_at = now() + timedelta(minutes=5)
                source.last_error = run.message
                session.commit()
        return False


@celery_app.task(
    name="bnc.collect_source",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=150,
    time_limit=180,
)
def collect_source(run_id: str) -> dict:
    try:
        return collect_run(uuid.UUID(run_id), SessionLocal)
    except Exception:
        # Keep the job observable even if an unexpected error escapes collection.
        # If the database itself is unavailable, the scheduler recovers the lease.
        try:
            with SessionLocal() as session:
                run = session.get(CollectionRun, uuid.UUID(run_id))
                if run and run.status in {"PENDING", "RUNNING"}:
                    run.status, run.message, run.finished_at = (
                        "FAILED",
                        "Worker collection failed; test the source and retry",
                        now(),
                    )
                    source = session.get(Source, run.source_id)
                    if source.collection_lock_id == run.id:
                        source.collection_lock_id = source.locked_until = None
                    source.next_collection_at = now() + timedelta(minutes=5)
                    session.commit()
        except Exception:
            pass
        raise


def reserve_due(session) -> list[uuid.UUID]:
    """Claim due work under DB locks; duplicate beat ticks cannot enqueue it twice."""
    abandoned = session.scalars(
        select(CollectionRun)
        .where(
            CollectionRun.status.in_(["PENDING", "RUNNING"]),
            CollectionRun.updated_at < now() - timedelta(minutes=10),
        )
        .with_for_update(skip_locked=True)
    ).all()
    for run in abandoned:
        run.status, run.message, run.finished_at = (
            "FAILED",
            "Collection timed out; scheduled for retry",
            now(),
        )
        source = session.get(Source, run.source_id)
        if source.collection_lock_id == run.id:
            source.collection_lock_id = source.locked_until = None
        source.next_collection_at = now()
    sources = session.scalars(
        select(Source)
        .where(
            Source.active.is_(True),
            Source.source_type != "manual",
            Source.extraction_mode == "metadata",
            Source.rights != "prohibited",
            Source.next_collection_at <= now(),
        )
        .order_by(Source.next_collection_at, Source.id)
        .limit(100)
        .with_for_update(skip_locked=True)
    ).all()
    ids = []
    for source in sources:
        if not collectible(source):
            continue
        if session.scalar(
            select(CollectionRun.id)
            .where(
                CollectionRun.source_id == source.id,
                CollectionRun.status.in_(["PENDING", "RUNNING"]),
            )
            .limit(1)
        ):
            continue
        run = CollectionRun(source_id=source.id)
        session.add(run)
        session.flush()
        source.next_collection_at = next_collection(source)
        audit(session, "source.collection_scheduled", source.id, run_id=str(run.id))
        ids.append(run.id)
    session.commit()
    return ids


@celery_app.task(name="bnc.collect_due_sources")
def collect_due_sources() -> dict:
    with SessionLocal() as session:
        ids = reserve_due(session)
    queued = sum(enqueue(run_id) for run_id in ids)
    return {"queued": queued}
