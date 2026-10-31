"""Account case file: the four whys, each item a cited fact, a labelled inference or an unknown."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from trigger_point.models.context import Mode
from trigger_point.models.evidence import Evidence
from trigger_point.research.people import PersonaMatch
from trigger_point.research.scoring import ScoreBreakdown

CASE_VERSION = "case-v1"
Route = Literal["cold_email", "research_more", "do_not_contact"]


class CaseItem(BaseModel):
    text: str
    kind: Literal["fact", "inference", "unknown"]
    evidence_ids: list[str] = Field(default_factory=list)


class AccountCase(BaseModel):
    id: str
    version: str = CASE_VERSION
    research_id: str
    context_id: str
    account_id: int
    account_name: str | None
    account_domain: str | None
    seller_name: str
    mode: Mode
    created_at: datetime
    reference_date: date
    why_account: list[CaseItem]
    why_person: list[CaseItem]
    why_now: list[CaseItem]
    why_us: list[CaseItem]
    hypotheses: list[CaseItem]
    coverage_gaps: list[str]
    warm_path: str
    recommended_route: Route
    route_reason: str
    next_best_action: str
    score: ScoreBreakdown
    recipient: PersonaMatch | None
    hook_evidence_ids: list[str]
    seller_evidence_ids: list[str]
    expires_on: date | None
    evidence: list[Evidence]
