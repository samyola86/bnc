"""Bounded metadata adapters. Public retrieval uses the existing SSRF/robots boundary."""

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urlencode, urlsplit

import httpx

from app.config import get_settings
from app.ingestion.network import Document, SourceError
from app.ingestion.parsing import ParsedFeed, article, iso_date, parse_feed

PROVIDERS = {"INSTAGRAM_ACCOUNT", "GDELT", "GOOGLE_NEWS"}


@dataclass
class DiscoveryBatch:
    document: Document
    feed: ParsedFeed
    cursor: dict = field(default_factory=dict)


class DiscoveryAdapter(Protocol):
    def collect(self, source, fetcher) -> DiscoveryBatch: ...


class AudienceProvider(Protocol):
    """Future authorized WordPress/Meta analytics share this observation interface."""

    def observations(self, topic: str, geography: str) -> list[dict]: ...


class GoogleTrends:
    def status(self):
        return {
            "provider": "google_trends",
            "status": "UNCONFIGURED",
            "reason": "Official authorized API access required; using newsroom coverage momentum",
        }

    def observations(self, topic, geography="BD"):
        return []  # Absence is unavailable, never synthetic zero search volume.


class GoogleNews:
    def collect(self, source, fetcher):
        config = source.provider_config
        query = urlencode(
            {
                "q": config.get("query", "Bangladesh"),
                "hl": config.get("hl", "en-BD"),
                "gl": config.get("gl", "BD"),
                "ceid": config.get("ceid", "BD:en"),
            }
        )
        document = fetcher.fetch("https://news.google.com/rss/search?" + query)
        parsed = parse_feed(document)
        # Google redirect links remain explicitly unresolved; never decode opaque tokens.
        return DiscoveryBatch(document, parsed)


class GDELT:
    def collect(self, source, fetcher):
        query = urlencode(
            {
                "query": source.provider_config.get("query", "Bangladesh"),
                "mode": "artlist",
                "format": "json",
                "maxrecords": 100,
                "timespan": "24h",
                "sort": "datedesc",
            }
        )
        document = fetcher.fetch("https://api.gdeltproject.org/api/v2/doc/doc?" + query)
        try:
            data = json.loads(document.body)
            if "articles" not in data:
                raise ValueError
            rows = data["articles"]
            if not isinstance(rows, list):
                raise ValueError
            parsed = ParsedFeed("GDELT discovery", [])
            for row in rows[:100]:
                try:
                    date = datetime.strptime(row.get("seendate", ""), "%Y%m%dT%H%M%SZ").replace(
                        tzinfo=UTC
                    )
                    candidate = article(
                        row["url"],
                        row["url"],
                        row["title"],
                        "",
                        published_at=None,
                        publisher_name=row.get("domain", ""),
                    )
                    candidate.provider_metadata = {
                        "gdelt_seen_at": date.isoformat(),
                        "timestamp_kind": "discovery_time",
                    }
                    parsed.articles.append(candidate)
                except (KeyError, ValueError, SourceError):
                    parsed.skipped += 1
            return DiscoveryBatch(document, parsed)
        except (ValueError, TypeError, AttributeError):
            raise SourceError("GDELT returned an invalid metadata response") from None

    def timeline(self, query, fetcher):
        url = "https://api.gdeltproject.org/api/v2/doc/doc?" + urlencode(
            {"query": query, "mode": "timelinevol", "format": "json", "timespan": "7d"}
        )
        data = json.loads(fetcher.fetch(url).body)
        return data.get("timeline", [])


def instagram_link(value):
    parts = urlsplit(value)
    if parts.scheme != "https" or parts.netloc not in {"www.instagram.com", "instagram.com"}:
        raise ValueError("Use an HTTPS Instagram post permalink")
    match = re.fullmatch(r"/(p|reel)/([A-Za-z0-9_-]{3,100})/?", parts.path)
    if not match or parts.query or parts.fragment:
        raise ValueError("Use a post or reel permalink without tracking parameters")
    return f"https://www.instagram.com/{match[1]}/{match[2]}/"


class Instagram:
    """Official Business Discovery only; no credential forwarding to source URLs."""

    def collect(self, source, fetcher=None, *, transport=None):
        settings = get_settings()
        if not settings.meta_instagram_token or not settings.meta_instagram_account_id:
            raise SourceError(
                "Instagram is unconfigured: Meta token and professional account ID required; "
                "add post links manually"
            )
        username = source.provider_config.get("username", "")
        if not re.fullmatch(r"[A-Za-z0-9_.]{1,30}", username):
            raise SourceError("Invalid Instagram username")
        if (
            not re.fullmatch(r"v[0-9]+\.[0-9]+", settings.meta_graph_version)
            or not settings.meta_instagram_account_id.isdigit()
        ):
            raise SourceError("Invalid backend Meta API configuration")
        after = getattr(source, "provider_cursor", {}).get("after", "")
        if after and not re.fullmatch(r"[A-Za-z0-9_=-]{1,2000}", after):
            raise SourceError("Invalid Instagram pagination cursor")
        page = f".after({after})" if after else ""
        fields = (
            f"business_discovery.username({username})"
            "{id,username,media.limit(50)"
            + page
            + "{id,caption,permalink,timestamp,media_type,like_count,comments_count}}"
        )
        url = f"https://graph.facebook.com/{settings.meta_graph_version}/{settings.meta_instagram_account_id}"
        try:
            with httpx.Client(
                timeout=25, transport=transport, follow_redirects=False, trust_env=False
            ) as client:
                response = client.get(
                    url,
                    params={"fields": fields},
                    headers={"Authorization": f"Bearer {settings.meta_instagram_token}"},
                )
            if response.status_code == 429:
                raise SourceError("Meta rate limit reached; collection backed off", retry_after=900)
            if response.status_code != 200:
                raise SourceError(
                    "Meta denied Business Discovery access; verify app permissions "
                    "and supported professional account"
                )
            if len(response.content) > 2 * 1024 * 1024:
                raise SourceError("Meta metadata response exceeds limit")
            identity = response.json().get("business_discovery")
            if not identity or identity.get("username", "").casefold() != username.casefold():
                raise SourceError(
                    "Instagram account is unavailable or unsupported by Business Discovery"
                )
            media = identity.get("media", {})
            parsed = ParsedFeed("Instagram @" + username, [])
            previous = getattr(source, "provider_cursor", {})
            since = iso_date(previous.get("since"))
            high_water = iso_date(previous.get("high_water")) or since
            reached_previous = False
            for post in media.get("data", [])[:50]:
                published = iso_date(post.get("timestamp"))
                if published and since and published <= since:
                    reached_previous = True
                    # Keep the fetched head page to refresh permitted engagement metrics;
                    # stop pagination at the old watermark. Existing post IDs deduplicate.
                if published:
                    high_water = max(high_water, published) if high_water else published
                link = instagram_link(post["permalink"])
                item = article(
                    post["id"],
                    link,
                    post.get("caption", "")[:180] or f"Post by @{username}",
                    post.get("caption", "")[:1200],
                    published_at=iso_date(post.get("timestamp")),
                    publisher_name="@" + username,
                )
                item.provider_metadata = {
                    k: post[k]
                    for k in ("id", "media_type", "like_count", "comments_count")
                    if k in post
                }
                parsed.articles.append(item)
            cursor = (
                media.get("paging", {}).get("cursors", {}).get("after")
                if media.get("paging", {}).get("next")
                else None
            )
            if reached_previous:
                cursor = None
            if cursor and cursor == after:
                raise SourceError("Meta repeated its pagination cursor; collection stopped")
            document = Document(source.url, 200, b"", {})
            return DiscoveryBatch(
                document,
                parsed,
                {
                    "after": cursor or "",
                    "checked_at": datetime.now(UTC).isoformat(),
                    "since": (
                        previous.get("since", "")
                        if cursor
                        else high_water.isoformat()
                        if high_water
                        else ""
                    ),
                    "high_water": high_water.isoformat() if high_water else "",
                },
            )
        except SourceError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise SourceError(
                "Instagram metadata retrieval failed; check account access and use manual links"
            ) from None


ADAPTERS = {"GDELT": GDELT(), "GOOGLE_NEWS": GoogleNews(), "INSTAGRAM_ACCOUNT": Instagram()}
