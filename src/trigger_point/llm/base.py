"""Provider-neutral structured LLM contract. Callers get a validated Pydantic object or an error."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel

from trigger_point.config import Mode

T = TypeVar("T", bound=BaseModel)

LlmErrorKind = Literal[
    "auth",
    "rate_limited",
    "server",
    "timeout",
    "network",
    "truncated",
    "invalid_output",
    "refusal",
    "replay_missing",
]


class LlmError(RuntimeError):
    def __init__(self, kind: LlmErrorKind, message: str) -> None:
        super().__init__(f"{kind}: {message}")
        self.kind = kind


@dataclass(frozen=True)
class LlmRequest(Generic[T]):
    task: str
    replay_key: str  # stable key for replay fixtures, e.g. the seller domain
    system: str
    user: str
    schema: type[T]
    max_tokens: int = 16_000


@dataclass(frozen=True)
class LlmUsage:
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int | None
    request_id: str | None
    latency_ms: int


@dataclass(frozen=True)
class LlmResponse(Generic[T]):
    output: T
    usage: LlmUsage | None
    mode: Mode


class StructuredLlm(Protocol):
    @property
    def mode(self) -> Mode: ...

    def complete(self, req: LlmRequest[T]) -> LlmResponse[T]: ...
