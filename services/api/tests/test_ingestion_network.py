import socket
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from app.ingestion import network
from app.ingestion.network import MAX_BYTES, SafeFetcher, SourceError, normalize_url, public_url


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/rss",
        "http://[::1]/rss",
        "http://169.254.169.254/metadata",
        "http://10.0.0.1/rss",
        "http://192.168.1.1/rss",
        "http://localhost/rss",
        "http://service.internal/rss",
        "ftp://example.com/rss",
        "file:///etc/passwd",
        "https://example.com:9000/rss",
        "https://user:password@example.com/rss",
        "https://example.com/rss?api_key=secret",
        "https://example.com/\r\nHost:localhost",
    ],
)
def test_private_urls_credentials_and_invalid_schemes_are_rejected(url):
    with pytest.raises(SourceError):
        public_url(url)


def test_url_normalization_preserves_story_identity():
    assert (
        normalize_url("https://EXAMPLE.com/story?id=1&utm_source=rss#top")
        == "https://example.com/story?id=1"
    )
    assert normalize_url("https://example.com/story?id=2") != normalize_url(
        "https://example.com/story?id=1"
    )


def test_mixed_public_private_dns_answers_are_rejected(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ],
    )
    with pytest.raises(SourceError, match="Private"):
        network.resolve_public("publisher.example", 443)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:4860:4860::8888", 443, 0, 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        ],
    )
    assert network.resolve_public("publisher.example", 443) == "93.184.216.34"


@pytest.fixture
def mock_http(monkeypatch):
    calls = []
    responses = {}
    original_client = httpx.Client

    def handler(request):
        calls.append(request)
        code, body, headers = responses.get(request.url.path, (404, b"", {}))
        return httpx.Response(code, stream=httpx.ByteStream(body), headers=headers)

    monkeypatch.setattr(network, "resolve_public", lambda *args: "93.184.216.34")
    monkeypatch.setattr(network, "throttle", lambda *args: None)
    monkeypatch.setattr(
        network.httpx,
        "Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    return calls, responses


def test_validated_ip_is_pinned_with_original_tls_hostname(mock_http):
    calls, responses = mock_http
    responses["/feed"] = (200, b"news", {})
    assert SafeFetcher().fetch("https://publisher.example/feed").body == b"news"
    request = calls[-1]
    assert request.url.host == "93.184.216.34"
    assert request.headers["host"] == "publisher.example"
    assert request.extensions["sni_hostname"] == "publisher.example"


def test_redirect_to_private_ip_is_rejected_before_following(mock_http):
    calls, responses = mock_http
    responses["/feed"] = (302, b"", {"location": "http://127.0.0.1/private"})
    with pytest.raises(SourceError):
        SafeFetcher().fetch("https://publisher.example/feed")
    assert len(calls) == 2  # robots and the initial feed; no private request.


def test_robots_policy_applies_before_fetch_and_to_redirect_paths(mock_http):
    calls, responses = mock_http
    responses["/robots.txt"] = (200, b"User-agent: *\nDisallow: /private\n", {})
    with pytest.raises(SourceError, match="disallows"):
        SafeFetcher().fetch("https://publisher.example/private")
    assert len(calls) == 1
    calls.clear()
    responses["/feed"] = (302, b"", {"location": "/private"})
    with pytest.raises(SourceError, match="disallows"):
        SafeFetcher().fetch("https://publisher.example/feed")
    assert all(request.url.path != "/private" for request in calls)


def test_oversized_and_compressed_documents_fail_safely(mock_http):
    _, responses = mock_http
    responses["/feed"] = (200, b"a" * (MAX_BYTES + 1), {})
    with pytest.raises(SourceError, match="2 MB"):
        SafeFetcher().fetch("https://publisher.example/feed")
    responses["/feed"] = (200, b"compressed", {"content-encoding": "gzip"})
    with pytest.raises(SourceError, match="uncompressed"):
        SafeFetcher().fetch("https://publisher.example/feed")


@pytest.mark.parametrize("status", [401, 403, 451, 429, 503])
def test_restricted_or_rate_limited_sources_are_not_bypassed(mock_http, status):
    calls, responses = mock_http
    responses["/feed"] = (status, b"restricted", {"retry-after": "3600"})
    with pytest.raises(SourceError) as error:
        SafeFetcher().fetch("https://publisher.example/feed")
    if status in {429, 503}:
        assert error.value.retry_after == 3600
    assert len(calls) == 2


def test_retry_after_http_date_is_respected(mock_http):
    _, responses = mock_http
    date = format_datetime(datetime.now(UTC) + timedelta(hours=1), usegmt=True)
    responses["/feed"] = (429, b"", {"retry-after": date})
    with pytest.raises(SourceError) as error:
        SafeFetcher().fetch("https://publisher.example/feed")
    assert 3590 <= error.value.retry_after <= 3600


def test_robot_request_rate_controls_the_shared_origin_limiter(mock_http, monkeypatch):
    _, responses = mock_http
    gaps = []
    monkeypatch.setattr(network, "throttle", lambda url, gap, deadline: gaps.append(gap))
    responses["/robots.txt"] = (200, b"User-agent: *\nRequest-rate: 1/3\n", {})
    responses["/feed"] = (200, b"news", {})
    SafeFetcher().fetch("https://publisher.example/feed")
    assert gaps == [1.0, 3.0]
