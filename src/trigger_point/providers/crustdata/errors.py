"""Typed Crustdata failures. An empty result is never an error; these are."""

from __future__ import annotations

from typing import Any, Literal

CrustdataErrorKind = Literal[
    "invalid_request",
    "auth",
    "insufficient_credits",
    "permission",
    "fields_denied",
    "not_found",
    "rate_limited",
    "server",
    "timeout",
    "network",
    "malformed_response",
    "budget_exceeded",
    "replay_missing",
]
RETRYABLE: frozenset[str] = frozenset({"rate_limited", "server", "timeout", "network"})


class CrustdataError(RuntimeError):
    def __init__(
        self,
        kind: CrustdataErrorKind,
        message: str,
        status: int | None = None,
        denied_fields: list[str] | None = None,
    ) -> None:
        super().__init__(f"crustdata {kind}: {message}")
        self.kind = kind
        self.status = status
        self.denied_fields = denied_fields or []

    @property
    def retryable(self) -> bool:
        return self.kind in RETRYABLE


_STATUS_KIND: dict[int, CrustdataErrorKind] = {
    400: "invalid_request",
    401: "auth",
    402: "insufficient_credits",
    403: "permission",
    404: "not_found",
}


def error_from_response(status: int, body: Any) -> CrustdataError:
    """Docs show three error shapes: {error:{type,message,metadata}}, {message} (401), and
    {error, description}. Parse all of them; never echo request headers."""
    message = f"HTTP {status}"
    metadata: Any = []
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            message = str(err.get("message") or message)
            metadata = err.get("metadata") or []
        elif isinstance(err, str):
            message = str(body.get("description") or body.get("reason") or err)
        elif "message" in body:
            message = str(body["message"])
    kind = _STATUS_KIND.get(status, "server" if status >= 500 else "invalid_request")
    denied: list[str] = []
    for item in metadata if isinstance(metadata, list) else []:
        if isinstance(item, dict):
            denied.extend(str(f) for f in item.get("denied_fields") or [])
    if status == 403 and denied:
        kind = "fields_denied"
    # Batch endpoints can put tens of KB of permitted fields into the message.
    return CrustdataError(kind, message[:500], status=status, denied_fields=denied)
