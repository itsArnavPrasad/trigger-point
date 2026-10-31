"""Bounded same-site crawl of the pages most likely to describe the business."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

from trigger_point.web.extract import extract_page
from trigger_point.web.fetcher import Fetcher, FetchStatus

_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
MAX_SITEMAP_LINKS = 200
# Earlier keywords rank higher. Matched against path segments.
PAGE_KEYWORDS = (
    "product",
    "platform",
    "features",
    "solutions",
    "use-cases",
    "pricing",
    "customers",
    "case-studies",
    "integrations",
    "about",
    "security",
    "why",
)
SKIP_SEGMENTS = {
    "login",
    "signin",
    "sign-in",
    "signup",
    "register",
    "privacy",
    "terms",
    "legal",
    "cookies",
    "cart",
    "account",
    "careers",
    "jobs",
}
ASSET_SUFFIXES = (
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".zip",
    ".mp4",
    ".css",
    ".js",
    ".xml",
    ".json",
)


@dataclass(frozen=True)
class PageRecord:
    url: str
    final_url: str
    fetch_status: FetchStatus
    retrieved_at: datetime
    http_status: int | None
    title: str | None
    text: str
    raw_sha256: str | None
    error: str | None


def _site(host: str) -> str:
    return host.lower().removeprefix("www.")


def _canonical(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    return f"{parts.scheme}://{(parts.hostname or '').lower()}{path or '/'}"


def _rank(url: str) -> int | None:
    segments = [s for s in urlsplit(url).path.lower().split("/") if s]
    if any(s in SKIP_SEGMENTS for s in segments):
        return None
    for i, kw in enumerate(PAGE_KEYWORDS):
        if segments and any(seg == kw or seg.startswith(kw) for seg in segments[:2]):
            return i
    return len(PAGE_KEYWORDS) + len(segments)


def select_pages(seed: str, links: list[str], max_pages: int = 8) -> list[str]:
    seed_parts = urlsplit(seed)
    seed_site = _site(seed_parts.hostname or "")
    seen = {_canonical(seed)}
    ranked: list[tuple[int, int, str]] = []
    for order, link in enumerate(links):
        parts = urlsplit(link)
        if parts.scheme not in ("http", "https") or _site(parts.hostname or "") != seed_site:
            continue
        if parts.query or parts.path.lower().endswith(ASSET_SUFFIXES):
            continue
        canonical = _canonical(link)
        rank = _rank(canonical)
        if rank is None or canonical in seen:
            continue
        seen.add(canonical)
        ranked.append((rank, order, canonical))
    ranked.sort()
    return [seed] + [url for _, _, url in ranked[: max(0, max_pages - 1)]]


def _record(url: str, fetcher: Fetcher, site: str | None = None) -> tuple[PageRecord, list[str]]:
    res = fetcher.fetch(url)
    if (
        res.status == "ok"
        and site is not None
        and _site(urlsplit(res.final_url).hostname or "") != site
    ):
        # Never credit a third party's page to the seller's URL.
        return PageRecord(
            url,
            res.final_url,
            "blocked_redirect",
            res.retrieved_at,
            res.http_status,
            None,
            "",
            None,
            "offsite_redirect",
        ), []
    if res.status != "ok":
        return PageRecord(
            url,
            res.final_url,
            res.status,
            res.retrieved_at,
            res.http_status,
            None,
            "",
            None,
            res.error,
        ), []
    page = extract_page(res.text, res.final_url)
    record = PageRecord(
        url,
        res.final_url,
        "ok",
        res.retrieved_at,
        res.http_status,
        page.title,
        page.text,
        res.sha256,
        None,
    )
    return record, page.links


def _sitemap_links(seed: str, fetcher: Fetcher) -> list[str]:
    """Pages the site lists but may not link. A regex, not an XML parser: the document is
    untrusted, and only the <loc> values are wanted."""
    parts = urlsplit(seed)
    res = fetcher.fetch(f"{parts.scheme}://{parts.netloc}/sitemap.xml")
    if res.status != "ok":
        return []
    return _LOC.findall(res.text)[:MAX_SITEMAP_LINKS]


def crawl_site(seed: str, fetcher: Fetcher, max_pages: int = 8) -> list[PageRecord]:
    seed_record, links = _record(seed, fetcher)
    if seed_record.fetch_status != "ok":
        return [seed_record]
    records = [seed_record]
    # The seed may redirect (e.g. to www. or a new domain); its final site defines "same site".
    site = _site(urlsplit(seed_record.final_url).hostname or "")
    links = links + _sitemap_links(seed_record.final_url, fetcher)
    for url in select_pages(seed_record.final_url, links, max_pages)[1:]:
        records.append(_record(url, fetcher, site)[0])
    return records
