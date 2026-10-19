"""Bounded public HTTP retrieval with DNS pinning and per-hop SSRF validation."""

import hashlib
import ipaddress
import socket
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
from redis import Redis, RedisError

from app.config import get_settings

USER_AGENT = "BNCFeedCollector/0.1"
MAX_BYTES = 2 * 1024 * 1024
TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
SECRET_KEYS = {
    "api_key",
    "api-key",
    "apikey",
    "access_token",
    "token",
    "password",
    "secret",
    "key",
    "signature",
    "authorization",
}

RATE_SCRIPT = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local gap = math.max(tonumber(ARGV[1]), tonumber(redis.call('GET', KEYS[2]) or '0'))
redis.call('SET', KEYS[2], gap, 'PX', 3600000)
local wait = tonumber(redis.call('GET', KEYS[1]) or '0') + gap - now
if wait > 0 then return wait end
redis.call('SET', KEYS[1], now, 'PX', 120000)
return 0
"""


def throttle(url: str, minimum_gap: float, deadline: float):
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    key = "bnc:fetch:" + hashlib.sha256(origin.encode()).hexdigest()
    try:
        with Redis.from_url(
            get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2
        ) as redis:
            while time.monotonic() < deadline:
                wait = redis.eval(RATE_SCRIPT, 2, key, key + ":gap", int(minimum_gap * 1000))
                if wait <= 0:
                    return
                time.sleep(min(wait / 1000, 0.5))
    except RedisError:
        raise SourceError("The collection rate limiter is unavailable; try again later") from None
    raise SourceError("Publisher rate limits require waiting; try this source later")


class SourceError(ValueError):
    def __init__(self, message: str, *, retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def public_url(value: str) -> str:
    try:
        parts = urlsplit(value.strip())
        host = (parts.hostname or "").encode("idna").decode().lower().rstrip(".")
        if parts.scheme not in {"http", "https"} or not host:
            raise ValueError
        if parts.username or parts.password or parts.port not in {None, 80, 443}:
            raise ValueError
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if "." not in host or any(c in host for c in "\\/%\x00\r\n "):
                raise ValueError from None
        else:
            if not address.is_global:
                raise ValueError
        if any(key.lower() in SECRET_KEYS for key, _ in parse_qsl(parts.query)):
            raise SourceError("Keep API keys and credentials out of source URLs")
        authority = f"[{host}]" if ":" in host else host
        if parts.port and parts.port != (443 if parts.scheme == "https" else 80):
            authority += f":{parts.port}"
        result = urlunsplit((parts.scheme, authority, parts.path or "/", parts.query, ""))
        if len(result) > 2048 or any(c in value for c in "\x00\r\n"):
            raise ValueError
        return result
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, SourceError):
            raise
        raise SourceError("Use a public HTTP(S) URL without credentials or custom ports") from None


def normalize_url(value: str) -> str:
    parts = urlsplit(public_url(value))
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_KEYS
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(sorted(query)), ""))


def resolve_public(host: str, port: int) -> str:
    try:
        addresses = {
            entry[4][0] for entry in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        }
    except OSError:
        raise SourceError("The source hostname could not be resolved") from None
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise SourceError("Private, local, or reserved network destinations are not allowed")
    # Prefer IPv4 on the local Docker network while validating every DNS answer.
    return sorted(addresses, key=lambda address: (ipaddress.ip_address(address).version, address))[
        0
    ]


@dataclass
class Document:
    url: str
    status: int
    body: bytes
    headers: dict[str, str]


class SafeFetcher:
    def __init__(self):
        self.deadline = time.monotonic() + 45
        self.robots: dict[str, RobotFileParser | None] = {}
        self.minimum_gaps: dict[str, float] = {}

    def _request(self, url: str, headers: dict | None = None, *, check_redirects=False) -> Document:
        """Connect to the validated IP, preserving Host, TLS SNI, and certificate checks.

        Redirects are handled here, never by HTTPX, so each new target is validated.
        Environment proxies are disabled to avoid resolving the hostname elsewhere.
        """
        for _ in range(4):
            if time.monotonic() > self.deadline:
                raise SourceError("The source took too long to respond")
            url = public_url(url)
            parts = urlsplit(url)
            origin = f"{parts.scheme}://{parts.netloc}"
            throttle(url, self.minimum_gaps.get(origin, 1.0), self.deadline)
            host = parts.hostname
            address = resolve_public(host, parts.port or (443 if parts.scheme == "https" else 80))
            pinned = httpx.URL(url).copy_with(host=address)
            request_headers = {
                "User-Agent": USER_AGENT,
                "Accept-Encoding": "identity",
                "Host": parts.netloc,
                **(headers or {}),
            }
            try:
                with httpx.Client(timeout=8, follow_redirects=False, trust_env=False) as client:
                    with client.stream(
                        "GET", pinned, headers=request_headers, extensions={"sni_hostname": host}
                    ) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location:
                                raise SourceError("The source returned an invalid redirect")
                            url = public_url(urljoin(url, location))
                            if check_redirects:
                                self._allowed(url)
                            # Do not leak validators across an origin change.
                            headers = None
                            continue
                        if response.headers.get("content-encoding", "identity") != "identity":
                            raise SourceError("The source ignored the uncompressed response limit")
                        length = response.headers.get("content-length", "0")
                        if not length.isdigit() or int(length) > MAX_BYTES:
                            raise SourceError("The source response exceeds the 2 MB metadata limit")
                        body = bytearray()
                        for chunk in response.iter_raw(chunk_size=16384):
                            if len(body) + len(chunk) > MAX_BYTES:
                                raise SourceError(
                                    "The source response exceeds the 2 MB metadata limit"
                                )
                            if time.monotonic() > self.deadline:
                                raise SourceError("The source took too long to respond")
                            body.extend(chunk)
                        return Document(
                            url, response.status_code, bytes(body), dict(response.headers)
                        )
            except (httpx.HTTPError, OSError):
                raise SourceError(
                    "Could not retrieve the source securely; try again later"
                ) from None
        raise SourceError("The source redirected too many times")

    def _allowed(self, url: str):
        parts = urlsplit(public_url(url))
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self.robots:
            document = self._request(f"{origin}/robots.txt")
            if document.status in {401, 403, 429} or document.status >= 500:
                raise SourceError("Collection is restricted or robots.txt is unavailable")
            if document.status in {404, 410}:
                self.robots[origin] = None
            elif document.status == 200:
                parser = RobotFileParser()
                parser.parse(document.body.decode("utf-8", errors="replace").splitlines())
                self.robots[origin] = parser
            else:
                raise SourceError("Could not confirm source collection permissions")
        parser = self.robots[origin]
        if parser and not parser.can_fetch(USER_AGENT, url):
            raise SourceError("This source disallows collection in robots.txt")
        if parser:
            rate = parser.request_rate(USER_AGENT)
            delay = max(
                parser.crawl_delay(USER_AGENT) or 0,
                rate.seconds / rate.requests if rate and rate.requests > 0 else 0,
            )
            if delay > 10 or time.monotonic() + delay > self.deadline:
                raise SourceError("This source requires a longer crawl delay; use a licensed feed")
            self.minimum_gaps[origin] = max(1.0, delay)

    def fetch(self, url: str, headers: dict | None = None) -> Document:
        self._allowed(url)
        document = self._request(url, headers, check_redirects=True)
        if document.status in {401, 403, 451}:
            raise SourceError("Access is restricted; no bypass or article scraping was attempted")
        if document.status == 429 or document.status >= 500:
            retry = document.headers.get("retry-after", "")
            retry_seconds = int(retry) if retry.isdigit() else None
            if retry_seconds is None and retry:
                try:
                    date = parsedate_to_datetime(retry)
                    date = date.replace(tzinfo=date.tzinfo or UTC)
                    retry_seconds = max(0, int((date - datetime.now(UTC)).total_seconds()))
                except (ValueError, TypeError, OverflowError):
                    pass
            raise SourceError(
                "The source is rate limited or temporarily unavailable",
                retry_after=min(retry_seconds, 86400) if retry_seconds is not None else None,
            )
        if document.status not in {200, 304}:
            raise SourceError(f"The source returned HTTP {document.status}")
        return document
