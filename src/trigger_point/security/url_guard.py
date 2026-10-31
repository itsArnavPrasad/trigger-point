"""SSRF policy for fetching user-supplied and discovered URLs.

Every URL (including every redirect hop) must pass `check_url` before a request is made.
Known limitation: the check resolves DNS before the HTTP client connects, so a hostile DNS
server could still rebind between check and connect. Pinning the connection to the checked
address is tracked in docs/PROJECT_STATUS.md.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlsplit, urlunsplit

Resolver = Callable[[str], list[str]]

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {None, 80, 443}
BLOCKED_HOST_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa")
NAT64_WELL_KNOWN = ipaddress.ip_network("64:ff9b::/96")
NAT64_LOCAL = ipaddress.ip_network("64:ff9b:1::/48")
IPV4_COMPATIBLE = ipaddress.ip_network("::/96")


class UnsafeUrlError(ValueError):
    def __init__(self, reason: str, url: str = "") -> None:
        super().__init__(f"unsafe url ({reason}): {url}")
        self.reason = reason
        self.url = url


def system_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return sorted({str(info[4][0]) for info in infos})


def _ip_is_public(raw: str) -> bool:
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address = ipaddress.ip_address(raw.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address):
        # Unwrap IPv6 forms that embed an IPv4 destination; refuse ones we cannot reason about.
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif ip in IPV4_COMPATIBLE or ip in NAT64_LOCAL or ip.teredo is not None:
            return False
        elif ip in NAT64_WELL_KNOWN:
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        elif ip.sixtofour is not None:
            ip = ip.sixtofour
    return ip.is_global and not ip.is_multicast


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _resolve(host: str, url: str, resolver: Resolver) -> list[str]:
    try:
        addresses = resolver(host)
    except (OSError, UnicodeError) as exc:
        raise UnsafeUrlError("dns_failure", url) from exc
    if not addresses:
        raise UnsafeUrlError("dns_failure", url)
    return addresses


def normalize_seed_url(raw: str) -> str:
    text = raw.strip()
    if not text:
        raise UnsafeUrlError("empty", raw)
    if "://" not in text:
        text = "https://" + text
    parts = urlsplit(text)
    netloc = parts.netloc.lower()
    path = parts.path or "/"
    return urlunsplit((parts.scheme.lower(), netloc, path, parts.query, ""))


def check_url(url: str, resolver: Resolver = system_resolver) -> None:
    host = check_url_static(url)
    addresses = [host] if _is_ip_literal(host) else _resolve(host, url, resolver)
    for address in addresses:
        try:
            public = _ip_is_public(address)
        except ValueError as exc:
            raise UnsafeUrlError("ip_unparseable", url) from exc
        if not public:
            raise UnsafeUrlError("ip_not_public", url)


def check_url_static(url: str) -> str:
    """Checks everything that does not need DNS; returns the host. IP literals are checked."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise UnsafeUrlError("malformed", url) from exc
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeUrlError("scheme", url)
    if parts.username is not None or parts.password is not None:
        raise UnsafeUrlError("credentials", url)
    if port not in ALLOWED_PORTS:
        raise UnsafeUrlError("port", url)
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeUrlError("host_missing", url)
    if host == "localhost" or host.endswith(BLOCKED_HOST_SUFFIXES):
        raise UnsafeUrlError("host_blocked", url)
    if _is_ip_literal(host) and not _ip_is_public(host):
        raise UnsafeUrlError("ip_not_public", url)
    return host
