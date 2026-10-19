import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from app.api.health import router as health_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.ingestion import router as ingestion_router
from app.api.v1.stories import router as stories_router
from app.config import get_settings

logger = logging.getLogger("bnc.api")
app = FastAPI(title="BNC Newsroom API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def trace_request(request: Request, call_next):
    request.state.request_id = str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


def error(request: Request, code: str, message: str, status: int):
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return error(request, f"HTTP_{exc.status_code}", str(exc.detail), exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return error(request, "VALIDATION_ERROR", "Invalid request", 422)


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
    logger.error("Database request failed: request_id=%s", request.state.request_id)
    return error(request, "DATABASE_UNAVAILABLE", "Editorial database unavailable", 503)


app.include_router(health_router)
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(ingestion_router, prefix="/api/v1")
app.include_router(stories_router, prefix="/api/v1")
