import uuid

from sqlalchemy import select

from app.ai.models import AIJob
from app.ai.provider import GenerationError, generate
from app.ai.service import expire_job
from app.db import models  # noqa: F401 - register FK models in standalone workers
from app.db.session import SessionLocal
from app.ingestion.models import Source
from app.ingestion.service import audit, now
from app.workers.celery_app import celery_app


def run_job(job_id, factory=SessionLocal):
    with factory() as session:
        job = session.scalar(select(AIJob).where(AIJob.id == job_id).with_for_update())
        if not job or job.status != "PENDING":
            return
        expire_job(job)
        for evidence in job.input_json["evidence"]:
            for credit in evidence.get("attributions", []):
                source = session.get(Source, uuid.UUID(credit["source_id"]))
                if (
                    not source
                    or source.rights not in {"metadata_only", "licensed", "owned"}
                    or source.extraction_mode != "metadata"
                ):
                    job.status, job.message, job.finished_at = (
                        "FAILED",
                        "Source permissions changed. Review rights and generate again",
                        now(),
                    )
        if job.status == "FAILED":
            session.commit()
            return
        job.status, job.message = "RUNNING", "Generating a draft for human review"
        packet, model = job.input_json, job.model
        session.commit()
    try:
        result, usage = generate(packet, model)
        status, message = "SUCCEEDED", "Preview ready. Review, apply and save explicitly"
    except GenerationError as exc:
        result, usage, status, message = None, None, "FAILED", str(exc)
    except Exception:
        # Provider exceptions can contain secrets or source text. Never expose them.
        result, usage, status, message = (
            None,
            None,
            "FAILED",
            "AI worker failed. Your writing is unchanged; retry later",
        )
    with factory() as session:
        job = session.scalar(select(AIJob).where(AIJob.id == job_id).with_for_update())
        if job.status != "RUNNING":
            return
        job.result, job.usage, job.status, job.message = result, usage, status, message
        job.finished_at = now()
        audit(
            session, "ai.completed", job.story_id, job.editor_id, job_id=str(job.id), status=status
        )
        session.commit()


@celery_app.task(name="bnc.generate_draft", soft_time_limit=115, time_limit=130)
def generate_draft(job_id: str):
    run_job(uuid.UUID(job_id), SessionLocal)


def enqueue(job_id):
    try:
        generate_draft.apply_async(args=[str(job_id)], task_id=str(job_id), retry=False)
        return True
    except Exception:
        with SessionLocal() as session:
            job = session.get(AIJob, job_id)
            if job and job.status == "PENDING":
                job.status, job.message, job.finished_at = (
                    "FAILED",
                    "AI queue unavailable. Check Redis and the worker",
                    now(),
                )
                session.commit()
        return False
