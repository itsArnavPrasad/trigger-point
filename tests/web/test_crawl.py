from datetime import UTC, datetime

from trigger_point.web.crawl import crawl_site, select_pages
from trigger_point.web.fetcher import FetchResult

SEED = "https://acme.com/"


def test_select_pages_keeps_same_site_and_ranks_by_relevance() -> None:
    links = [
        "https://acme.com/blog/post-1",
        "https://acme.com/pricing",
        "https://www.acme.com/customers",
        "https://other.com/pricing",
        "mailto:sales@acme.com",
        "https://acme.com/whitepaper.pdf",
        "https://acme.com/pricing#faq",
        "https://acme.com/login?next=/",
        "https://acme.com/product/",
    ]
    chosen = select_pages(SEED, links, max_pages=4)
    assert chosen[0] == SEED
    assert "https://acme.com/pricing" in chosen
    assert "https://www.acme.com/customers" in chosen
    assert "https://acme.com/product" in chosen
    assert len(chosen) == 4
    assert all("other.com" not in u and "pdf" not in u and "#" not in u for u in chosen)
    assert chosen.index("https://acme.com/pricing") < len(chosen)
    assert "https://acme.com/blog/post-1" not in chosen


def test_select_pages_dedupes_trailing_slash_and_seed() -> None:
    chosen = select_pages(
        SEED, ["https://acme.com", "https://acme.com/about/", "https://acme.com/about"]
    )
    assert chosen == [SEED, "https://acme.com/about"]


class StubFetcher:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def fetch(self, url: str) -> FetchResult:
        self.calls.append(url)
        now = datetime(2026, 10, 31, tzinfo=UTC)
        if url in self.pages:
            return FetchResult(url, url, "ok", now, 200, "text/html", self.pages[url], "h" * 64)
        return FetchResult(url, url, "http_error", now, 404, error="http_404")


def test_crawl_records_failures_and_successes() -> None:
    fetcher = StubFetcher(
        {
            SEED: '<title>Acme</title><a href="/pricing">p</a><a href="/about">a</a>'
            "<p>Home text</p>",
            "https://acme.com/pricing": "<p>Plans from $99</p>",
        }
    )
    records = crawl_site(SEED, fetcher, max_pages=8)
    by_url = {r.url: r for r in records}
    assert by_url[SEED].fetch_status == "ok" and by_url[SEED].title == "Acme"
    assert "Plans from $99" in by_url["https://acme.com/pricing"].text
    assert by_url["https://acme.com/about"].fetch_status == "http_error"
    assert by_url["https://acme.com/about"].text == ""


def test_crawl_with_failed_seed_returns_single_failed_record() -> None:
    records = crawl_site(SEED, StubFetcher({}), max_pages=8)
    assert [r.fetch_status for r in records] == ["http_error"]


def test_sitemap_pages_are_crawled_when_the_page_does_not_link_them() -> None:
    from datetime import UTC, datetime

    from trigger_point.web.crawl import crawl_site
    from trigger_point.web.fetcher import FetchResult

    now = datetime(2026, 10, 31, tzinfo=UTC)
    site = {
        "https://a.example/": "<html><body><p>Home</p></body></html>",
        "https://a.example/sitemap.xml": (
            "<urlset><url><loc>https://a.example/pricing</loc></url>"
            "<url><loc>https://other.example/x</loc></url>"
            "<url><loc>https://a.example/legal/terms</loc></url></urlset>"
        ),
        "https://a.example/pricing": "<html><body><p>Pricing</p></body></html>",
    }

    class Stub:
        def fetch(self, url: str) -> FetchResult:
            if url in site:
                return FetchResult(url, url, "ok", now, 200, "text/html", site[url], "h")
            return FetchResult(url, url, "http_error", now, 404, error="nope")

    urls = [p.url for p in crawl_site("https://a.example/", Stub())]
    assert "https://a.example/pricing" in urls
    assert not any("other.example" in u or "legal" in u or "sitemap" in u for u in urls)
