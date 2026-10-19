"""Run interactively on the trusted API host: python -m app.auth.bootstrap."""

from getpass import getpass

from sqlalchemy import func, select, text

from app.auth.models import User
from app.auth.routes import Account
from app.auth.security import cipher, password_hash
from app.db.session import SessionLocal
from app.ingestion.service import audit


def bootstrap(session, account, password):
    if session.bind.dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(834120719)"))
    if session.scalar(select(func.count()).select_from(User).where(User.role == "SUPERADMIN")):
        raise ValueError("Bootstrap is closed: a Superadmin account already exists")
    cipher()  # MFA enrollment must be possible before creating the first privileged account.
    user = User(**account.model_dump(), password_hash=password_hash(password))
    session.add(user)
    session.flush()
    audit(session, "auth.superadmin_bootstrapped", user.id, user.id)
    session.commit()
    return user.id


def main():
    account = Account(
        name=input("Name: "),
        email=input("Email: "),
        username=input("Username: "),
        role="SUPERADMIN",
    )
    password = getpass("Password (12+ characters): ")
    if password != getpass("Confirm password: "):
        raise SystemExit("Passwords differ")
    with SessionLocal() as session:
        bootstrap(session, account, password)
    print("Superadmin created. Sign in and enroll your authenticator before newsroom access.")


if __name__ == "__main__":
    main()
