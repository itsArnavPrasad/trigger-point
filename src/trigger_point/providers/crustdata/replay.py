"""Transport-level record/replay, so replay exercises the same client, parsing and normalisation.

Fixtures live at `<root>/<endpoint_slug>/<request_hash[:16]>.json` and carry a `_source` label
("recorded live ..." or "synthetic demo fixture ..."); replay never invents a response.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from trigger_point.providers.crustdata.client import ReplayMissing, request_key

KEPT_HEADERS = ("x-credits-used", "x-ratelimit-remaining", "x-ratelimit-limit", "content-type")


def _slug(path: str) -> str:
    return path.strip("/").replace("/", "_")


def _key_for(request: httpx.Request) -> tuple[str, str]:
    body: Any = json.loads(request.content) if request.content else None
    params = dict(request.url.params) or None
    return _slug(request.url.path), request_key(request.method, request.url.path, body, params)


class ReplayTransport(httpx.BaseTransport):
    def __init__(self, root: Path) -> None:
        self._root = root

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        slug, key = _key_for(request)
        path = self._root / slug / f"{key[:16]}.json"
        if not path.is_file():
            raise ReplayMissing(f"no Crustdata replay fixture {slug}/{key[:16]}.json")
        saved = json.loads(path.read_text())
        # Replayed responses never claim credits were spent now.
        headers = {k: v for k, v in saved.get("headers", {}).items() if k != "x-credits-used"}
        headers["x-credits-used"] = "0"
        headers["x-trigger_point-replay-source"] = str(saved.get("_source", "unlabelled fixture"))
        return httpx.Response(saved["status"], json=saved["body"], headers=headers)


class RecordingTransport(httpx.BaseTransport):
    """Wraps a live transport and writes each response as a replay fixture."""

    def __init__(
        self,
        inner: httpx.BaseTransport,
        root: Path,
        source_label: str = "recorded live from api.crustdata.com",
    ) -> None:
        self._inner = inner
        self._root = root
        self._label = source_label

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self._inner.handle_request(request)
        response.read()
        if request.url.path.startswith("/person/contact"):
            return response  # real people's emails and phones never become a committed fixture
        slug, key = _key_for(request)
        target = self._root / slug / f"{key[:16]}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            body: Any = response.json()
        except json.JSONDecodeError:
            return response
        target.write_text(
            json.dumps(
                {
                    "_source": self._label,
                    "_request": {
                        "method": request.method,
                        "path": request.url.path,
                        "body": json.loads(request.content) if request.content else None,
                    },
                    "status": response.status_code,
                    "headers": {
                        k: v for k, v in response.headers.items() if k.lower() in KEPT_HEADERS
                    },
                    "body": body,
                },
                indent=2,
            )
            + "\n"
        )
        return response
