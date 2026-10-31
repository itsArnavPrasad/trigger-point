"""Bounded, SSRF-checked page fetching. Network outcomes are results, never exceptions."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import urljoin, urlsplit

import httpx

from trigger_point.security.url_guard import Resolver, UnsafeUrlError, check_url, system_resolver

FetchStatus = Literal[
    "ok",
    "http_error",
    "blocked",
    "blocked_redirect",
    "timeout",
    "too_large",
    "unsupported_type",
    "network_error",
]
ALLOWED_CONTENT_TYPES = (
    "text/html",
    "text/plain",
    "application/xhtml+xml",
    "application/xml",  # sitemaps
    "text/xml",
)
USER_AGENT = "TriggerPointBot/0.1 (+business-context research; respects bounded crawling)"


@dataclass(frozen=True)
class FetchResult:
    url: str
    final_url: str
    status: FetchStatus
    retrieved_at: datetime
    http_status: int | None = None
    content_type: str | None = None
    text: str = ""
    sha256: str | None = None
    error: str | None = None


class Fetcher(Protocol):
    def fetch(self, url: str) -> FetchResult: ...


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def default_http_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(10.0),
        headers={"user-agent": USER_AGENT, "accept": "text/html,text/plain;q=0.9"},
        follow_redirects=False,
        trust_env=False,  # never route through environment proxies
    )


class SafeHttpFetcher:
    def __init__(
        self,
        client: httpx.Client,
        resolver: Resolver = system_resolver,
        max_bytes: int = 2_000_000,
        max_redirects: int = 5,
        total_seconds: float = 20.0,
        clock: Callable[[], datetime] = _utcnow,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._resolver = resolver
        self._max_bytes = max_bytes
        self._max_redirects = max_redirects
        self._clock = clock
        self._total_seconds = total_seconds
        self._monotonic = monotonic

    def fetch(self, url: str) -> FetchResult:
        current = url
        deadline = self._monotonic() + self._total_seconds
        for hop in range(self._max_redirects + 1):
            if self._monotonic() > deadline:
                return self._result(url, current, "timeout", error="total_deadline_exceeded")
            try:
                check_url(current, self._resolver)
            except UnsafeUrlError as exc:
                status: FetchStatus = "blocked" if hop == 0 else "blocked_redirect"
                return self._result(url, current, status, error=exc.reason)
            try:
                with self._client.stream("GET", current, follow_redirects=False) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            return self._result(
                                url,
                                current,
                                "http_error",
                                resp.status_code,
                                error="redirect_without_location",
                            )
                        current = urljoin(current, location)
                        continue
                    return self._read(url, current, resp, deadline)
            except httpx.TimeoutException:
                return self._result(url, current, "timeout", error="timeout")
            except (httpx.HTTPError, httpx.InvalidURL) as exc:
                return self._result(url, current, "network_error", error=type(exc).__name__)
        return self._result(url, current, "http_error", error="too_many_redirects")

    def _read(self, url: str, final_url: str, resp: httpx.Response, deadline: float) -> FetchResult:
        content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        if resp.status_code >= 400:
            return self._result(
                url,
                final_url,
                "http_error",
                resp.status_code,
                content_type,
                error=f"http_{resp.status_code}",
            )
        if content_type not in ALLOWED_CONTENT_TYPES:
            return self._result(
                url,
                final_url,
                "unsupported_type",
                resp.status_code,
                content_type,
                error=content_type or "missing_content_type",
            )
        body = bytearray()
        for chunk in resp.iter_bytes():
            body.extend(chunk)
            if self._monotonic() > deadline:
                return self._result(
                    url,
                    final_url,
                    "timeout",
                    resp.status_code,
                    content_type,
                    error="total_deadline_exceeded",
                )
            if len(body) > self._max_bytes:
                return self._result(
                    url,
                    final_url,
                    "too_large",
                    resp.status_code,
                    content_type,
                    error=f"exceeds_{self._max_bytes}_bytes",
                )
        text = bytes(body).decode(resp.encoding or "utf-8", errors="replace")
        return FetchResult(
            url=url,
            final_url=final_url,
            status="ok",
            retrieved_at=self._clock(),
            http_status=resp.status_code,
            content_type=content_type,
            text=text,
            sha256=_sha256(text),
        )

    def _result(
        self,
        url: str,
        final_url: str,
        status: FetchStatus,
        http_status: int | None = None,
        content_type: str | None = None,
        error: str | None = None,
    ) -> FetchResult:
        return FetchResult(
            url=url,
            final_url=final_url,
            status=status,
            retrieved_at=self._clock(),
            http_status=http_status,
            content_type=content_type,
            error=error,
        )


class FixtureFetcher:
    """Replay fetcher: serves recorded pages from `root/<host>/<path>/index.html`.

    `retrieved_at` is the recording time from `root/<host>/_meta.json`, never "now".
    """

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def fetch(self, url: str) -> FetchResult:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        site = (self._root / host).resolve()
        recorded_at = self._recorded_at(site)
        if not host or not site.is_relative_to(self._root) or recorded_at is None:
            return FetchResult(url, url, "http_error", _utcnow(), error="fixture_missing")
        page_dir = (site / parts.path.strip("/")).resolve()
        candidate = page_dir / "index.html"
        if not candidate.is_relative_to(site) or not candidate.is_file():
            return FetchResult(url, url, "http_error", recorded_at, 404, error="fixture_missing")
        text = candidate.read_text(encoding="utf-8")
        return FetchResult(url, url, "ok", recorded_at, 200, "text/html", text, _sha256(text))

    @staticmethod
    def _recorded_at(site: Path) -> datetime | None:
        meta = site / "_meta.json"
        if not meta.is_file():
            return None
        return datetime.fromisoformat(json.loads(meta.read_text())["recorded_at"])
