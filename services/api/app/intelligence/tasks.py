from datetime import timedelta

from sqlalchemy import select, update

from app.db.session import SessionLocal
from app.ingestion.models import IngestedItem
from app.ingestion.service import aware, now
from app.intelligence.analytics import WINDOWS, attach, measure
from app.intelligence.classification import classify, controls, eligible_items
from app.intelligence.models import IntelligenceUsage, ItemAnalysis, StoryCluster
from app.workers.celery_app import celery_app


def run_cycle(factory=SessionLocal, *, force=False):
    with factory() as session:
        row, config = controls(session, lock=True)
        if row.lease_until and aware(row.lease_until) > now():
            session.rollback()
            return {"status": "BUSY"}
        if (
            not force
            and row.last_cycle
            and aware(row.last_cycle) + timedelta(minutes=config.cadence_minutes) > now()
        ):
            session.rollback()
            return {"status": "NOT_DUE"}
        row.lease_until = now() + timedelta(minutes=10)
        row.last_cycle = now()
        session.execute(
            update(IntelligenceUsage)
            .where(
                IntelligenceUsage.status == "RESERVED",
                IntelligenceUsage.created_at < now() - timedelta(minutes=10),
            )
            .values(status="UNKNOWN", error="Worker lease expired; reserved cost retained")
        )
        ids = session.scalars(
            select(IngestedItem.id)
            .where(IngestedItem.id.in_(eligible_items()))
            .outerjoin(ItemAnalysis, ItemAnalysis.item_id == IngestedItem.id)
            .order_by(
                ItemAnalysis.id.is_not(None),
                IngestedItem.bangladesh_relevance.desc(),
                IngestedItem.created_at.desc(),
            )
            .limit(config.cycle_limit)
        ).all()
        session.commit()
    processed = 0
    try:
        for index, item_id in enumerate(ids):
            processed += int(classify(factory, item_id, allow_ai=index < config.ai_cycle_limit))
            with factory() as session:
                # Cycle lease serializes cluster assignment across workers.
                attach(session, session.get(IngestedItem, item_id))
                session.commit()
        with factory() as session:
            for cluster in session.scalars(
                select(StoryCluster)
                .where(StoryCluster.last_activity >= now() - timedelta(days=14))
                .order_by(StoryCluster.last_activity.desc())
                .limit(500)
            ):
                for window in WINDOWS:
                    measure(session, cluster, window)
            row, _ = controls(session, lock=True)
            row.lease_until = None
            session.commit()
        return {"status": "SUCCEEDED", "processed": processed}
    except Exception:
        with factory() as session:
            row, _ = controls(session, lock=True)
            row.lease_until = None
            session.commit()
        raise


@celery_app.task(name="bnc.intelligence_cycle", soft_time_limit=540, time_limit=570)
def intelligence_cycle():
    return run_cycle()
