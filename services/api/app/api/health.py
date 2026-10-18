from fastapi import APIRouter, HTTPException
from redis import Redis

from app.config import get_settings
from app.db.session import check_database

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def ready() -> dict[str, str]:
    try:
        check_database()
        with Redis.from_url(
            get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2
        ) as client:
            client.ping()
    except Exception:
        raise HTTPException(status_code=503, detail="Dependencies are unavailable") from None
    return {"status": "ready"}
