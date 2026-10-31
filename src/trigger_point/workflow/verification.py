"""Evidence audit (audit-v1): deterministic checks from docs/EVIDENCE_AND_VERIFICATION.md.

It proves what code can prove: a source exists, the record is about this entity, it has a date,
and it is inside the 120-day policy. It does not prove a page says what the excerpt says."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from trigger_point.cases.models import AccountCase
from trigger_point.drafts.models import CampaignDraft
from trigger_point.models.evidence import Evidence

AUDIT_VERSION = "audit-v1"
MAX_AGE_DAYS = 120
UNDATED_OK = {"seller_website", "user_provided"}  # facts about the seller, not timing signals
EvidenceStatus = Literal[
    "verified", "user_provided", "stale", "undated", "entity_mismatch", "unverifiable"
]


class EvidenceCheck(BaseModel):
    evidence_id: str
    status: EvidenceStatus
    reasons: list[str] = Field(default_factory=list)
    age_days: int | None = None
    method: str = AUDIT_VERSION


def _has_source(e: Evidence) -> bool:
    return (e.source_url or "").startswith(("http://", "https://")) or bool(e.provider_ref)


def _entity_ok(e: Evidence, account_id: str, person_ids: set[str]) -> bool:
    if e.entity_type == "seller":
        return True
    return e.entity_id == account_id or (e.entity_type == "person" and e.entity_id in person_ids)


def audit_evidence(
    e: Evidence,
    account_id: str,
    today: date,
    now: datetime,
    person_ids: set[str] | None = None,
) -> EvidenceCheck:
    if e.source_kind == "user_provided":
        return EvidenceCheck(evidence_id=e.id, status="user_provided")
    dated = e.event_on or e.as_of
    age = (today - dated).days if dated else None
    reasons: list[str] = []
    if not _has_source(e):
        reasons.append("no_source")
    if not (e.excerpt or "").strip():
        reasons.append("no_excerpt")
    if e.retrieved_at > now or (age is not None and age < 0):
        reasons.append("future_date")
    if reasons:
        return EvidenceCheck(evidence_id=e.id, status="unverifiable", reasons=reasons, age_days=age)
    if not _entity_ok(e, account_id, person_ids or set()):
        return EvidenceCheck(
            evidence_id=e.id, status="entity_mismatch", reasons=["entity_mismatch"], age_days=age
        )
    if e.source_kind in UNDATED_OK:
        return EvidenceCheck(evidence_id=e.id, status="verified", age_days=age)
    if age is None:
        return EvidenceCheck(evidence_id=e.id, status="undated", reasons=["no_event_or_as_of_date"])
    if age > MAX_AGE_DAYS:
        return EvidenceCheck(evidence_id=e.id, status="stale", reasons=["too_old"], age_days=age)
    return EvidenceCheck(evidence_id=e.id, status="verified", age_days=age)


class GateFinding(BaseModel):
    code: str
    message: str


class GateResult(BaseModel):
    passed: bool
    findings: list[GateFinding]
    version: str = "gate-v1"


def quality_gate(
    draft: CampaignDraft,
    case: AccountCase,
    statuses: dict[str, str],
    earlier_drafts: list[CampaignDraft],
) -> GateResult:
    """The last deterministic check before a human sees the draft. `statuses` is the audit
    result by evidence id; `earlier_drafts` is everything else on record."""
    findings: list[GateFinding] = []

    def fail(code: str, message: str) -> None:
        findings.append(GateFinding(code=code, message=message))

    if draft.status != "verified":
        fail("draft_not_verified", f"the outreach verifier left this draft {draft.status}")
    if draft.sending != "disabled":
        fail("sending_enabled", "a draft must never be able to send")
    if case.score.status != "qualified":
        fail("not_qualified", f"the account is {case.score.status}")
    if case.recommended_route != "cold_email":
        fail("wrong_route", f"the case routes to {case.recommended_route}")
    if case.expires_on is not None and case.expires_on < case.reference_date:
        fail("case_expired", f"the case expired on {case.expires_on.isoformat()}")
    ok = {"verified", "user_provided"}
    if statuses.get(draft.hook_evidence_id) not in ok:
        fail("hook_not_verified", "the hook's evidence did not pass the audit")
    for claim in draft.claims:
        if claim.kind != "fact":
            continue
        if not claim.evidence_ids:
            fail("uncited_fact", f"no evidence for: {claim.text[:80]}")
        elif any(statuses.get(e) not in ok for e in claim.evidence_ids):
            fail("unverified_fact", f"evidence failed the audit for: {claim.text[:80]}")
    for other in earlier_drafts:
        same_person = other.recipient_person_id == draft.recipient_person_id
        if same_person and other.id != draft.id and other.status == "approved":
            fail("duplicate_recipient", "an approved draft to this person already exists")
            break
    return GateResult(passed=not findings, findings=findings)
