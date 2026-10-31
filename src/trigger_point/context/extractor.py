"""Business-context extraction: one bounded structured-LLM call, re-validated into the domain."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ValidationError

from trigger_point.config import Mode
from trigger_point.context.prompt import SYSTEM_PROMPT, build_user_message
from trigger_point.llm.base import LlmError, LlmRequest, LlmUsage, StructuredLlm
from trigger_point.models.context import CLAIM_LIST_FIELDS, ContextClaim, ContextDraft
from trigger_point.web.crawl import PageRecord

TASK = "context_extraction"


class ExtractionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExtractionResult:
    draft: ContextDraft
    usage: LlmUsage | None
    mode: Mode


class ContextExtractor(Protocol):
    def extract(self, seed_url: str, goal: str, pages: list[PageRecord]) -> ExtractionResult: ...


# Wire schema for structured output: flat and constraint-light. The domain model re-validates.
class LlmClaim(BaseModel):
    text: str
    kind: Literal["fact", "inference"]
    source_url: str
    excerpt: str
    confidence: Literal["high", "medium", "low"]


class LlmContextDraft(BaseModel):
    company_name: LlmClaim | None
    product_summary: list[LlmClaim]
    value_propositions: list[LlmClaim]
    use_cases: list[LlmClaim]
    target_segments: list[LlmClaim]
    buyer_personas: list[LlmClaim]
    customer_pains: list[LlmClaim]
    differentiators: list[LlmClaim]
    proof_points: list[LlmClaim]
    competitors: list[LlmClaim]
    exclusions: list[LlmClaim]
    unknowns: list[str]
    clarification_questions: list[str]


def _to_claim(c: LlmClaim) -> ContextClaim:
    return ContextClaim(
        text=c.text,
        kind=c.kind,
        source_url=c.source_url or None,
        excerpt=c.excerpt or None,
        confidence=c.confidence,
    )


def to_domain_draft(wire: LlmContextDraft) -> ContextDraft:
    fields: dict[str, Any] = {
        name: [_to_claim(c) for c in getattr(wire, name)] for name in CLAIM_LIST_FIELDS
    }
    return ContextDraft(
        company_name=_to_claim(wire.company_name) if wire.company_name else None,
        unknowns=wire.unknowns,
        # Keep the three highest-impact questions; the prompt asks for at most three.
        clarification_questions=wire.clarification_questions[:3],
        **fields,
    )


class LlmContextExtractor:
    def __init__(self, llm: StructuredLlm) -> None:
        self._llm = llm

    def extract(self, seed_url: str, goal: str, pages: list[PageRecord]) -> ExtractionResult:
        if not any(p.fetch_status == "ok" and p.text for p in pages):
            raise ExtractionError("no usable pages to extract from")
        domain = (urlsplit(seed_url).hostname or "").removeprefix("www.")
        req = LlmRequest(
            task=TASK,
            replay_key=domain,
            system=SYSTEM_PROMPT,
            user=build_user_message(seed_url, goal, pages),
            schema=LlmContextDraft,
        )
        try:
            resp = self._llm.complete(req)
        except LlmError as exc:
            raise ExtractionError(str(exc)) from exc
        try:
            draft = to_domain_draft(resp.output)
        except ValidationError as exc:
            raise ExtractionError(f"model output invalid for domain model: {exc}") from exc
        return ExtractionResult(draft=draft, usage=resp.usage, mode=resp.mode)
