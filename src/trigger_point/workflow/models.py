"""Mission workflow contracts: states, the fixed task plan, tasks, approvals and events."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = 1
MAX_ATTEMPTS = 3
TASK_LEASE_SECONDS = 15 * 60

MissionState = Literal[
    "RECEIVED",
    "PROFILE_REVIEW",
    "ICP_READY",
    "ACCOUNTS_FOUND",
    "SIGNALS_RESEARCHED",
    "PEOPLE_MAPPED",
    "EVIDENCE_VERIFIED",
    "CAMPAIGN_DRAFTED",
    "USER_APPROVAL",
    "COMPLETE",
    "WAITING_FOR_INPUT",
    "FAILED",
    "CANCELLED",
    "NEEDS_RETRY",
]
FLOW: tuple[MissionState, ...] = (
    "RECEIVED",
    "PROFILE_REVIEW",
    "ICP_READY",
    "ACCOUNTS_FOUND",
    "SIGNALS_RESEARCHED",
    "PEOPLE_MAPPED",
    "EVIDENCE_VERIFIED",
    "CAMPAIGN_DRAFTED",
    "USER_APPROVAL",
    "COMPLETE",
)
TERMINAL: frozenset[str] = frozenset({"COMPLETE", "FAILED", "CANCELLED"})

TaskStatus = Literal["queued", "running", "waiting_approval", "succeeded", "failed", "cancelled"]
EventStatus = Literal[
    "queued", "running", "waiting_approval", "succeeded", "failed", "cancelled", "info"
]
ApprovalGate = Literal["business_profile", "icp_plan", "campaign_draft"]
ApprovalStatus = Literal["pending", "approved", "rejected", "expired"]
Role = Literal[
    "mission-director",
    "icp-strategist",
    "account-scout",
    "signal-analyst",
    "buying-committee-mapper",
    "evidence-auditor",
    "campaign-architect",
    "quality-gatekeeper",
]
TaskKind = Literal[
    "profile_intake",
    "build_strategy",
    "build_icp",
    "discover_accounts",
    "research_signals",
    "map_committee",
    "verify_evidence",
    "score_account",
    "draft_campaign",
    "quality_gate",
    "user_review",
]


@dataclass(frozen=True)
class TaskSpec:
    kind: TaskKind
    role: Role
    title: str
    from_state: MissionState
    to_state: MissionState | None  # None: the mission stays where it is
    gate: ApprovalGate | None = None  # must be approved before the task may start
    after: TaskKind | None = None  # must have succeeded before the task may start


TASK_PLAN: tuple[TaskSpec, ...] = (
    TaskSpec(
        "profile_intake",
        "mission-director",
        "Read the seller's website",
        "RECEIVED",
        "PROFILE_REVIEW",
    ),
    TaskSpec(
        "build_strategy",
        "icp-strategist",
        "Draft market, value proposition and GTM motion",
        "PROFILE_REVIEW",
        None,
        gate="business_profile",
    ),
    TaskSpec(
        "build_icp",
        "icp-strategist",
        "Propose the ideal customer profile",
        "PROFILE_REVIEW",
        "ICP_READY",
        gate="business_profile",
    ),
    TaskSpec(
        "discover_accounts",
        "account-scout",
        "Find target companies",
        "ICP_READY",
        "ACCOUNTS_FOUND",
        gate="icp_plan",
    ),
    TaskSpec(
        "research_signals",
        "signal-analyst",
        "Find dated buying signals",
        "ACCOUNTS_FOUND",
        "SIGNALS_RESEARCHED",
    ),
    TaskSpec(
        "map_committee",
        "buying-committee-mapper",
        "Find the relevant people",
        "SIGNALS_RESEARCHED",
        "PEOPLE_MAPPED",
    ),
    TaskSpec(
        "verify_evidence",
        "evidence-auditor",
        "Audit evidence against sources",
        "PEOPLE_MAPPED",
        "EVIDENCE_VERIFIED",
    ),
    TaskSpec(
        "score_account",
        "evidence-auditor",
        "Select the top scored account",
        "EVIDENCE_VERIFIED",
        None,
    ),
    TaskSpec(
        "draft_campaign",
        "campaign-architect",
        "Draft the first touch from verified evidence",
        "EVIDENCE_VERIFIED",
        "CAMPAIGN_DRAFTED",
        after="score_account",
    ),
    TaskSpec(
        "quality_gate",
        "quality-gatekeeper",
        "Check relevance, evidence, duplicates and policy",
        "CAMPAIGN_DRAFTED",
        None,
    ),
    TaskSpec(
        "user_review",
        "mission-director",
        "Wait for the user's review of the draft",
        "USER_APPROVAL",
        "COMPLETE",
    ),
)
SPECS: dict[str, TaskSpec] = {s.kind: s for s in TASK_PLAN}
GATE_STATES: dict[str, MissionState] = {
    "business_profile": "PROFILE_REVIEW",
    "icp_plan": "ICP_READY",
    "campaign_draft": "CAMPAIGN_DRAFTED",
}

EventType = Literal[
    "mission.created",
    "mission.updated",
    "mission.waiting",
    "mission.completed",
    "mission.failed",
    "mission.cancelled",
    "task.queued",
    "task.started",
    "task.retrying",
    "task.completed",
    "task.failed",
    "tool.started",
    "tool.completed",
    "evidence.created",
    "evidence.verified",
    "artifact.published",
    "approval.requested",
    "approval.resolved",
    "strategy.versioned",
]


class WorkflowMission(BaseModel):
    id: str
    website_url: str
    goal: str
    state: MissionState = "RECEIVED"
    resume_state: MissionState | None = None  # where NEEDS_RETRY / WAITING_FOR_INPUT came from
    wait_reason: str | None = None
    failure: str | None = None
    mode: str  # live | replay | mixed, stamped from the providers configured for this run
    provider_modes: dict[str, str] = Field(default_factory=dict)
    context_id: str | None = None
    gtm_mission_id: str | None = None
    discovery_id: str | None = None
    research_id: str | None = None
    selected_account_id: int | None = None
    draft_id: str | None = None
    created_at: datetime
    updated_at: datetime


class TaskError(BaseModel):
    kind: str
    message: str
    retryable: bool


class WorkflowTask(BaseModel):
    id: str
    mission_id: str
    kind: TaskKind
    role: Role
    title: str
    position: int
    status: TaskStatus = "queued"
    attempt: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    output: dict[str, Any] = Field(default_factory=dict)
    artifact_ids: list[str] = Field(default_factory=list)
    error: TaskError | None = None


class WorkflowApproval(BaseModel):
    id: str
    mission_id: str
    gate: ApprovalGate
    target_hash: str
    summary: str
    status: ApprovalStatus = "pending"
    requested_at: datetime
    decided_at: datetime | None = None
    decided_by: str | None = None
    reason: str | None = None


_RENAMED = {
    "mission.started": "mission.created",
    "mission.state_changed": "mission.updated",
    "evidence.added": "evidence.created",
    "approval.required": "approval.requested",
}


class WorkflowEvent(BaseModel):
    schema_version: int = SCHEMA_VERSION
    event_id: str
    seq: int
    event_type: EventType
    occurred_at: datetime
    recorded_at: datetime
    mission_id: str
    task_id: str | None = None
    agent_id: str | None = None
    role: Role | None = None
    status: EventStatus = "info"
    summary: str
    artifact_ids: list[str] = Field(default_factory=list)
    correlation_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _read_older_rows(cls, raw: Any) -> Any:
        """Rows written before the spec's event names. The log is append-only, so it is read,
        not rewritten."""
        if isinstance(raw, dict) and "type" in raw:
            raw = {**raw, "event_type": _RENAMED.get(raw["type"], raw["type"])}
            raw.pop("type")
            raw.setdefault("recorded_at", raw.get("occurred_at"))
        return raw


class EvidenceRecord(BaseModel):
    """What the Office shows for one piece of evidence. `event_on` and `retrieved_at` stay
    separate: a fetch time is never an event date."""

    id: str
    account: str | None = None
    entity_type: str
    claim: str
    source_url: str | None
    provider_ref: str | None
    publisher: str | None
    event_on: date | None
    as_of: date | None
    retrieved_at: datetime
    excerpt: str | None
    verification_status: str = "unverified"
    verification_reasons: list[str] = Field(default_factory=list)


def stable_id(prefix: str, *parts: object) -> str:
    raw = json.dumps([str(p) for p in parts], separators=(",", ":"))
    return f"{prefix}_{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


_REDACTIONS = (
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    re.compile(r"\b(?:sk|pk|rk|ghp|xox[abp])[-_][A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)bearer\s+\S+"),
    re.compile(r"(?i)(?:api[_-]?key|token|secret|password)\s*[=:]\s*\S+"),
    re.compile(r"\+\d[\d\s().-]{7,}\d"),
)


def safe_text(text: str, limit: int = 240) -> str:
    """Event text: contact data and anything key-shaped removed, then clamped."""
    for pattern in _REDACTIONS:
        text = pattern.sub("[redacted]", text)
    return " ".join(text.split())[:limit]
