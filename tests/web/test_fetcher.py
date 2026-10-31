from datetime import UTC, datetime
from pathlib import Path

import httpx

from trigger_point.web.fetcher import FixtureFetcher, SafeHttpFetcher

PUBLIC = {"acme.com": ["93.184.216.34"], "cdn.acme.com": ["93.184.216.35"]}


def resolver(host: str) -> list[str]:
    return PUBLIC.get(host, ["10.0.0.9"])


def fetcher_for(handler: httpx.MockTransport, **kw: int) -> SafeHttpFetcher:
    return SafeHttpFetcher(httpx.Client(transport=handler), resolver=resolver, **kw)


def html(body: str, status: int = 200, **headers: str) -> httpx.Response:
    return httpx.Response(
        status, headers={"content-type": "text/html; charset=utf-8", **headers}, text=body
    )


def test_success_records_hash_and_aware_timestamp() -> None:
    f = fetcher_for(httpx.MockTransport(lambda r: html("<p>hi</p>")))
    res = f.fetch("https://acme.com/")
    assert res.status == "ok"
    assert res.http_status == 200
    assert res.text == "<p>hi</p>"
    assert res.sha256 is not None and len(res.sha256) == 64
    assert res.retrieved_at.tzinfo is not None


def test_initial_private_url_is_blocked_without_request() -> None:
    calls: list[str] = []

    def handler(r: httpx.Request) -> httpx.Response:
        calls.append(str(r.url))
        return html("x")

    res = fetcher_for(httpx.MockTransport(handler)).fetch("http://intranet.acme.test/")
    assert res.status == "blocked"
    assert calls == []


def test_redirect_to_metadata_ip_is_blocked_and_never_requested() -> None:
    calls: list[str] = []

    def handler(r: httpx.Request) -> httpx.Response:
        calls.append(str(r.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/"})

    res = fetcher_for(httpx.MockTransport(handler)).fetch("https://acme.com/")
    assert res.status == "blocked_redirect"
    assert calls == ["https://acme.com/"]


def test_safe_relative_redirect_is_followed() -> None:
    def handler(r: httpx.Request) -> httpx.Response:
        if r.url.path == "/":
            return httpx.Response(301, headers={"location": "/home"})
        return html("home")

    res = fetcher_for(httpx.MockTransport(handler)).fetch("https://acme.com/")
    assert res.status == "ok"
    assert res.final_url == "https://acme.com/home"


def test_too_many_redirects() -> None:
    def handler(r: httpx.Request) -> httpx.Response:
        n = int(r.url.params.get("n", "0"))
        return httpx.Response(302, headers={"location": f"https://acme.com/?n={n + 1}"})

    res = fetcher_for(httpx.MockTransport(handler), max_redirects=5).fetch("https://acme.com/")
    assert res.status == "http_error"
    assert res.error == "too_many_redirects"


def test_oversized_body_is_rejected() -> None:
    f = fetcher_for(httpx.MockTransport(lambda r: html("x" * 2000)), max_bytes=1000)
    res = f.fetch("https://acme.com/")
    assert res.status == "too_large"
    assert res.text == ""


def test_non_html_content_type_is_rejected() -> None:
    def handler(r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF")

    assert fetcher_for(httpx.MockTransport(handler)).fetch("https://acme.com/a").status == (
        "unsupported_type"
    )


def test_timeout_is_a_result_not_an_exception() -> None:
    def handler(r: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=r)

    assert fetcher_for(httpx.MockTransport(handler)).fetch("https://acme.com/").status == "timeout"


def test_connect_error_is_network_error() -> None:
    def handler(r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=r)

    res = fetcher_for(httpx.MockTransport(handler)).fetch("https://acme.com/")
    assert res.status == "network_error"


def test_http_404_is_http_error() -> None:
    res = fetcher_for(httpx.MockTransport(lambda r: html("nope", 404))).fetch("https://acme.com/x")
    assert res.status == "http_error"
    assert res.http_status == 404


def test_fixture_fetcher_reads_recorded_pages(tmp_path: Path) -> None:
    site = tmp_path / "acme.example"
    (site / "pricing").mkdir(parents=True)
    (site / "_meta.json").write_text('{"recorded_at": "2026-10-31T00:00:00+00:00"}')
    (site / "index.html").write_text("<h1>Home</h1>")
    (site / "pricing" / "index.html").write_text("<h1>Pricing</h1>")
    f = FixtureFetcher(tmp_path)
    home = f.fetch("https://acme.example/")
    assert home.status == "ok" and "Home" in home.text
    assert home.retrieved_at == datetime(2026, 10, 31, tzinfo=UTC)
    assert "Pricing" in f.fetch("https://acme.example/pricing").text
    missing = f.fetch("https://acme.example/nope")
    assert missing.status == "http_error" and missing.error == "fixture_missing"


def test_fixture_fetcher_refuses_path_traversal(tmp_path: Path) -> None:
    (tmp_path / "secret.html").write_text("secret")
    (tmp_path / "acme.example").mkdir()
    res = FixtureFetcher(tmp_path).fetch("https://acme.example/../secret.html")
    assert res.status != "ok"
