"""Idempotent inactive publisher registrations: python -m app.intelligence.provision."""

from sqlalchemy import or_, select, text

from app.db import models  # noqa: F401 - CLI needs all referenced tables registered.
from app.db.session import SessionLocal
from app.ingestion.models import Source
from app.ingestion.schemas import SourceInput
from app.ingestion.service import audit, now, probe

PUBLISHERS = [
    ("bbc-top", "BBC News", "https://feeds.bbci.co.uk/news/rss.xml"),
    ("bbc-world", "BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("bbc-business", "BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("bbc-tech", "BBC Technology", "https://feeds.bbci.co.uk/news/technology/rss.xml"),
    ("bbc-asia", "BBC Asia", "https://feeds.bbci.co.uk/news/world/asia/rss.xml"),
    ("tbs", "The Business Standard", "https://www.tbsnews.net/top-news/rss.xml"),
]


def provision(session, *, test=False):
    if session.bind.dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(834120720)"))
    created = []
    for key, publisher, feed in PUBLISHERS + [
        ("cnn", "CNN", "https://edition.cnn.com/"),
        ("reuters", "Reuters", "https://www.reuters.com/"),
    ]:
        if session.scalar(
            select(Source.id).where(
                or_(
                    Source.provision_key == key,
                    Source.url == feed,
                    Source.feed_url == feed,
                    Source.publisher == publisher,
                )
            )
        ):
            continue
        reference = key in {"cnn", "reuters"}
        body = SourceInput(
            publisher=publisher,
            url=feed,
            feed_url=None if reference else feed,
            source_type="manual" if reference else "rss",
            language="en",
            active=False,
            extraction_mode="reference_only" if reference else "metadata",
            rights="unverified",
            notes=(
                "Provisioned inactive. Superadmin must verify permissions "
                "and availability before activation."
            ),
        )
        source = Source(**body.model_dump(), homepage=feed, provision_key=key)
        if test and not reference:
            result = probe(source)
            source.health, source.last_checked = result["health"], now()
            source.last_error = None if result["supported"] else result["message"]
        session.add(source)
        session.flush()
        audit(session, "source.provisioned_inactive", source.id)
        created.append({"publisher": publisher, "health": source.health or "UNTESTED"})
    session.commit()
    return created


if __name__ == "__main__":
    with SessionLocal() as session:
        for result in provision(session, test=True):
            print(result)
