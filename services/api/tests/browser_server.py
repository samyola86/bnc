"""Opt-in browser test server. Always uses a new disposable PostgreSQL schema."""

# ruff: noqa: E402
import os
import uuid
from contextlib import asynccontextmanager

from cryptography.fernet import Fernet

if os.environ.get("BNC_BROWSER_TEST") != "1":
    raise RuntimeError("This test-only server requires BNC_BROWSER_TEST=1")

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

schema = "bnc_browser_test_" + uuid.uuid4().hex
admin = create_engine(os.environ["DATABASE_URL"])
with admin.begin() as connection:
    connection.execute(CreateSchema(schema))
os.environ["DATABASE_URL"] = (
    make_url(os.environ["DATABASE_URL"])
    .update_query_dict({"options": f"-csearch_path={schema}"})
    .render_as_string(hide_password=False)
)
os.environ["AUTH_ORIGIN"] = "http://localhost:3002"
os.environ["AUTH_COOKIE_SECURE"] = "false"
os.environ["AUTH_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

from app.auth.models import User
from app.auth.security import password_hash
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app

Base.metadata.create_all(engine)
with SessionLocal() as session:
    for name, role in (
        ("browserwriter", "CONTENT_WRITER"),
        ("browsereditor", "EDITOR"),
        ("browseradmin", "SUPERADMIN"),
    ):
        session.add(
            User(
                name=name,
                username=name,
                email=f"{name}@example.test",
                role=role,
                password_hash=password_hash("browser-test-password"),
            )
        )
    session.commit()


@asynccontextmanager
async def lifespan(app):
    try:
        yield
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()


app.router.lifespan_context = lifespan
