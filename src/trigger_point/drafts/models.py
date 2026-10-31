"""Outreach drafts. A draft is never sent by Trigger Point; approval records intent only."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from trigger_point.models.context import Mode


class DraftClaim(BaseModel):
    text: str
    kind: Literal["fact", "inference"]
    evidence_ids: list[str]


class FollowUpStep(BaseModel):
    day_offset: int
    angle: str
    evidence_ids: list[str]


class DraftWire(BaseModel):
    """What the LLM returns. The verifier, not the model, decides whether it is usable."""

    subject: str
    body: str
    hook_evidence_id: str
    proof_point_evidence_id: str  # "" when no proof point is used
    claims: list[DraftClaim]
    follow_ups: list[FollowUpStep]


class Finding(BaseModel):
    code: str
    severity: Literal["error", "warning"]
    message: str


class VerifierAttempt(BaseModel):
    attempt: int
    outcome: Literal["pass", "fail"]
    findings: list[Finding]
    source: Literal["llm", "llm_revision", "human_edit"]


DraftStatus = Literal["verified", "rejected", "approved"]


def content_hash(recipient_person_id: int, channel: str, subject: str, body: str) -> str:
    raw = json.dumps([recipient_person_id, channel, subject, body], separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


class CampaignDraft(BaseModel):
    id: str
    case_id: str
    research_id: str
    account_id: int
    account_name: str | None
    recipient_person_id: int
    recipient_name: str | None
    recipient_title: str | None
    channel: Literal["email"] = "email"
    subject: str
    body: str
    hook_evidence_id: str
    proof_point_evidence_id: str | None
    claims: list[DraftClaim]
    follow_ups: list[FollowUpStep]
    content_hash: str
    status: DraftStatus
    verifier_log: list[VerifierAttempt]
    mode: Mode
    llm_calls: list[dict[str, object]] = Field(default_factory=list)
    initiated_by: str = "ui"
    created_at: datetime
    approved_at: datetime | None = None
    approved_by: str | None = None
    approved_hash: str | None = None
    sending: Literal["disabled"] = "disabled"
