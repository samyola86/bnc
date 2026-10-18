from celery import Celery

from app.config import get_settings

celery_app = Celery("bnc", broker=get_settings().redis_url)
celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    beat_schedule={},
)


@celery_app.task(name="bnc.healthcheck")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
