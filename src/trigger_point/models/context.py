"""Seller BusinessContext: each item is a quoted fact, a labelled inference, or user input."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ClaimKind = Literal["fact", "inference", "user_provided"]
GroundingStatus = Literal["pending", "supported", "unsupported", "not_applicable"]
Confidence = Literal["high", "medium", "low"]
ContextStatus = Literal["draft", "review_required", "approved", "archived"]
Mode = Literal["live", "replay"]
RunMode = Literal["live", "replay", "mixed"]
Readability = Literal["ok", "thin", "none"]

CLAIM_LIST_FIELDS = (
    "product_summary",
    "value_propositions",
    "use_cases",
    "target_segments",
    "buyer_personas",
    "customer_pains",
    "differentiators",
    "proof_points",
    "competitors",
    "exclusions",
)


class ContextClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1, max_length=600)
    kind: ClaimKind
    source_url: str | None = None
    excerpt: str | None = Field(default=None, max_length=600)
    confidence: Confidence
    status: GroundingStatus = "pending"
    status_reason: str | None = None
    verification_method: str | None = None

    @field_validator("text", mode="before")
    @classmethod
    def _collapse_whitespace(cls, v: object) -> object:
        return " ".join(v.split()) if isinstance(v, str) else v

    @model_validator(mode="after")
    def _facts_cite_a_source(self) -> Self:
        if self.kind == "fact" and not self.source_url:
            raise ValueError("a fact must cite source_url")
        return self


class ContextDraft(BaseModel):
    """What an extractor (LLM or replay) proposes. Untrusted until grounded and reviewed."""

    model_config = ConfigDict(extra="forbid")

    company_name: ContextClaim | None = None
    product_summary: list[ContextClaim] = Field(default_factory=list)
    value_propositions: list[ContextClaim] = Field(default_factory=list)
    use_cases: list[ContextClaim] = Field(default_factory=list)
    target_segments: list[ContextClaim] = Field(default_factory=list)
    buyer_personas: list[ContextClaim] = Field(default_factory=list)
    customer_pains: list[ContextClaim] = Field(default_factory=list)
    differentiators: list[ContextClaim] = Field(default_factory=list)
    proof_points: list[ContextClaim] = Field(default_factory=list)
    competitors: list[ContextClaim] = Field(default_factory=list)
    exclusions: list[ContextClaim] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list, max_length=3)


class PageRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    url: str
    final_url: str
    title: str | None
    fetch_status: str
    retrieved_at: datetime
    text_sha256: str | None
    http_status: int | None = None
    error: str | None = None


class BusinessContext(ContextDraft):
    website_url: str
    domain: str
    user_goal: str
    pages: list[PageRef] = Field(default_factory=list)
    mode: RunMode
    provider_modes: dict[str, Mode] = Field(default_factory=dict)
    run_id: str
    status: ContextStatus = "draft"
    version: int = 1
    approved_at: datetime | None = None
    approved_by: str | None = None
    readability: Readability = "ok"  # how much of the site could actually be read
    target_geography: str | None = None
    time_horizon: str | None = None

    @classmethod
    def from_draft(
        cls,
        draft: ContextDraft,
        *,
        website_url: str,
        domain: str,
        user_goal: str,
        pages: list[PageRef],
        mode: RunMode,
        run_id: str,
        provider_modes: dict[str, Mode] | None = None,
    ) -> BusinessContext:
        return cls(
            **draft.model_dump(),
            website_url=website_url,
            domain=domain,
            user_goal=user_goal,
            pages=pages,
            mode=mode,
            run_id=run_id,
            provider_modes=provider_modes or {},
        )

    def iter_claims(self) -> Iterator[tuple[str, ContextClaim]]:
        if self.company_name is not None:
            yield "company_name", self.company_name
        for name in CLAIM_LIST_FIELDS:
            for claim in getattr(self, name):
                yield name, claim

    def has_usable_facts(self) -> bool:
        """Something a human or a source actually stands behind."""
        return any(
            c.status == "supported" or c.kind == "user_provided" for _, c in self.iter_claims()
        )

    def unsupported_claims(self) -> list[ContextClaim]:
        return [c for _, c in self.iter_claims() if c.status == "unsupported"]
