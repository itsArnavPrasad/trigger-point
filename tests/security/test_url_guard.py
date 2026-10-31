import pytest

from trigger_point.security.url_guard import UnsafeUrlError, check_url, normalize_seed_url


def public(_: str) -> list[str]:
    return ["93.184.216.34"]


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("ftp://example.com/", "scheme"),
        ("file:///etc/passwd", "scheme"),
        ("javascript:alert(1)", "scheme"),
        ("http://user:pw@example.com/", "credentials"),
        ("http://example.com:8080/", "port"),
        ("http://localhost/", "host"),
        ("http://foo.localhost/", "host"),
        ("http://metadata.google.internal/", "host"),
        ("http://127.0.0.1/", "ip"),
        ("http://10.1.2.3/", "ip"),
        ("http://172.16.0.1/", "ip"),
        ("http://192.168.1.1/", "ip"),
        ("http://169.254.169.254/latest/meta-data/", "ip"),
        ("http://100.64.0.1/", "ip"),
        ("http://0.0.0.0/", "ip"),
        ("http://[::1]/", "ip"),
        ("http://[fc00::1]/", "ip"),
        ("http://[::ffff:127.0.0.1]/", "ip"),
        ("http:///nohost", "host"),
    ],
)
def test_rejects_unsafe_urls(url: str, reason: str) -> None:
    with pytest.raises(UnsafeUrlError) as exc:
        check_url(url, resolver=public)
    assert exc.value.reason.startswith(reason)


def test_rejects_hostname_resolving_to_any_private_address() -> None:
    with pytest.raises(UnsafeUrlError) as exc:
        check_url("https://evil.example.com/", resolver=lambda _: ["93.184.216.34", "10.0.0.5"])
    assert exc.value.reason.startswith("ip")


def test_dns_failure_is_reported_not_raised_as_oserror() -> None:
    def boom(_: str) -> list[str]:
        raise OSError("nxdomain")

    with pytest.raises(UnsafeUrlError) as exc:
        check_url("https://nope.example.com/", resolver=boom)
    assert exc.value.reason == "dns_failure"


def test_empty_resolution_is_rejected() -> None:
    with pytest.raises(UnsafeUrlError) as exc:
        check_url("https://nope.example.com/", resolver=lambda _: [])
    assert exc.value.reason == "dns_failure"


def test_accepts_public_https_url() -> None:
    check_url("https://example.com/pricing", resolver=public)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Acme.com/pricing#x", "https://acme.com/pricing"),
        ("  https://WWW.Acme.com  ", "https://www.acme.com/"),
        ("http://acme.com/a?b=1", "http://acme.com/a?b=1"),
    ],
)
def test_normalize_seed_url(raw: str, expected: str) -> None:
    assert normalize_seed_url(raw) == expected


def test_normalize_rejects_empty() -> None:
    with pytest.raises(UnsafeUrlError):
        normalize_seed_url("   ")


def test_static_check_skips_dns_but_blocks_private_literals() -> None:
    from trigger_point.security.url_guard import check_url_static

    check_url_static("https://supportpilot.example/")
    for bad in ("http://10.0.0.1/", "http://localhost/", "ftp://x.com/", "http://[::1]/"):
        with pytest.raises(UnsafeUrlError):
            check_url_static(bad)
