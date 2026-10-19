from celery import Celery

from app.config import get_settings

celery_app = Celery("bnc", broker=get_settings().redis_url, include=["app.ingestion.tasks"])
celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    beat_schedule={"collect-due-sources": {"task": "bnc.collect_due_sources", "schedule": 60.0}},
    task_publish_retry=False,
    broker_transport_options={
        "socket_connect_timeout": 3,
        "socket_timeout": 3,
        "visibility_timeout": 360,
    },
)


@celery_app.task(name="bnc.healthcheck")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
