import calendar
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin

import feedparser
from defusedxml import ElementTree

from app.ingestion.network import Document, SourceError, normalize_url, public_url


class MetadataHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text: list[str] = []
        self.links: list[str] = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in {"script", "style"}:
            self.ignored += 1
        if tag == "link" and "alternate" in (attributes.get("rel") or "").split():
            if attributes.get("type") in {
                "application/rss+xml",
                "application/atom+xml",
                "application/feed+json",
            } and attributes.get("href"):
                self.links.append(attributes["href"])

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.ignored = max(0, self.ignored - 1)

    def handle_data(self, data):
        if not self.ignored:
            self.text.append(data)


def plain_text(value: str, limit: int = 1200) -> str:
    parser = MetadataHTML()
    parser.feed(str(value or ""))
    return re.sub(r"\s+", " ", " ".join(parser.text)).strip()[:limit]


def iso_date(value: str | None) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
        return result.replace(tzinfo=result.tzinfo or UTC).astimezone(UTC)
    except (ValueError, TypeError):
        return None


@dataclass
class Article:
    guid: str
    url: str
    normalized_url: str
    title: str
    excerpt: str
    category: str
    author: str
    published_at: datetime | None
    content_hash: str
    publisher_name: str = ""


@dataclass
class ParsedFeed:
    title: str
    articles: list[Article]
    skipped: int = 0


def article(
    guid, url, title, excerpt, category="", author="", published_at=None, publisher_name=""
) -> Article:
    if not isinstance(title, str) or not isinstance(url, str) or not isinstance(excerpt, str):
        raise SourceError("The feed item contains invalid text metadata")
    url = public_url(url)
    canonical = normalize_url(url)
    title, excerpt = plain_text(title, 500), plain_text(excerpt)
    if not title:
        raise SourceError("An item has no headline")
    # Avoid merging unrelated updates with a generic headline and no summary.
    content = f"{title.casefold()}\n{excerpt.casefold()}" if excerpt else canonical
    return Article(
        hashlib.sha256(str(guid or canonical).encode()).hexdigest(),
        url,
        canonical,
        title,
        excerpt,
        plain_text(category, 100),
        plain_text(author, 200),
        published_at,
        hashlib.sha256(content.encode()).hexdigest(),
        plain_text(publisher_name, 200),
    )


def parse_feed(document: Document) -> ParsedFeed:
    body = document.body.lstrip().removeprefix(b"\xef\xbb\xbf").lstrip()
    if body.startswith(b"{"):
        try:
            data = json.loads(body)
        except (ValueError, UnicodeError):
            raise SourceError("The source returned invalid JSON") from None
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("version"), str)
            or data.get("version")
            not in {"https://jsonfeed.org/version/1", "https://jsonfeed.org/version/1.1"}
            or not isinstance(data.get("items"), list)
        ):
            raise SourceError(
                "This API needs a dedicated adapter. Only JSON Feed 1/1.1 is supported"
            )
        result = ParsedFeed(plain_text(data.get("title", ""), 500), [])
        for entry in data["items"][:500]:
            try:
                authors = entry.get("authors") or [entry.get("author") or {}]
                tags = entry.get("tags") or [""]
                if not isinstance(authors, list) or not isinstance(authors[0], dict):
                    raise SourceError("The feed item contains invalid author metadata")
                if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
                    raise SourceError("The feed item contains invalid category metadata")
                link = entry.get("url") or entry.get("external_url")
                if not link:
                    raise SourceError("The feed item has no original URL")
                result.articles.append(
                    article(
                        entry.get("id"),
                        urljoin(document.url, link),
                        entry.get("title"),
                        entry.get("summary") or entry.get("content_text") or "",
                        tags[0],
                        authors[0].get("name", ""),
                        iso_date(entry.get("date_published")),
                    )
                )
            except (SourceError, AttributeError, TypeError, IndexError):
                result.skipped += 1
        result.skipped += max(0, len(data["items"]) - 500)
        return result
    try:
        root = ElementTree.fromstring(body, forbid_dtd=True)
    except Exception:
        raise SourceError(
            "Not a valid, safe RSS/Atom feed; XML entities and DTDs are not accepted"
        ) from None
    if root.tag.split("}")[-1].lower() not in {"rss", "rdf", "feed"}:
        raise SourceError("No supported feed found. Add an RSS/Atom or JSON Feed URL")
    parsed = feedparser.parse(body)
    if parsed.get("bozo") or not parsed.get("version"):
        raise SourceError("The feed is malformed; ask the publisher for a valid feed URL")
    result = ParsedFeed(plain_text(parsed.feed.get("title", ""), 500), [])
    for entry in parsed.entries[:500]:
        try:
            date = entry.get("published_parsed") or entry.get("updated_parsed")
            source_metadata = entry.get("source") or {}
            publisher = source_metadata.get("title") or entry.get("publisher") or ""
            publisher = publisher if isinstance(publisher, str) else ""
            if not entry.get("link"):
                raise SourceError("The feed item has no original URL")
            result.articles.append(
                article(
                    entry.get("id"),
                    urljoin(document.url, entry.get("link") or ""),
                    entry.get("title"),
                    entry.get("summary", ""),
                    (entry.get("tags") or [{}])[0].get("term", ""),
                    entry.get("author", ""),
                    datetime.fromtimestamp(calendar.timegm(date), UTC) if date else None,
                    publisher,
                )
            )
        except (SourceError, ValueError, TypeError, OverflowError):
            result.skipped += 1
    result.skipped += max(0, len(parsed.entries) - 500)
    return result


def discover_links(document: Document) -> list[str]:
    parser = MetadataHTML()
    parser.feed(document.body.decode("utf-8", errors="replace"))
    links = []
    for link in parser.links:
        try:
            url = public_url(urljoin(document.url, link))
            if url not in links:
                links.append(url)
        except SourceError:
            continue
    return links[:5]
