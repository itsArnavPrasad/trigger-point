"""The ICP as a versioned strategy record: criteria with a kind, a basis and a confidence.

A plan alone is a search filter. This says which criteria must hold, which only help, what rules
an account out, and which of the spec's ten dimensions nobody has evidence for yet. Unknown
dimensions are listed as gaps, never filled in. Without customer data every ICP is a hypothesis.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from trigger_point.mission.models import GTMPlan

ICP_VERSION = "icp-v1"
DIMENSIONS = (
    "firmographic",
    "operational",
    "problem",
    "value",
    "budget",
    "technographic",
    "readiness",
    "buying_process",
    "reachability",
    "economics",
)
# Hard rejections in research/scoring.py
RULES = {
    "no_fresh_why_now": "Every timing signal is stale or missing",
    "no_relevant_buyer": "No person matching a persona works there now",
    "identity_unresolved": "The company's identity cannot be resolved",
}
CriterionKind = Literal["must_have", "preference", "disqualifier", "context"]


class IcpCriterion(BaseModel):
    dimension: str
    statement: str
    kind: CriterionKind
    basis: Literal["plan", "score_rule", "model_inference"]
    confidence: Literal["high", "medium", "low"]


class IcpVersion(BaseModel):
    mission_id: str
    plan_id: str
    version: int
    method: str = ICP_VERSION
    status: Literal["hypothesis", "approved", "superseded"] = "hypothesis"
    created_at: datetime
    author: str
    rationale: str
    changes: list[str] = Field(default_factory=list)
    target_hash: str
    icp_query: str
    criteria: list[IcpCriterion]
    personas: list[dict[str, str | None]]
    gaps: list[str]
    assumptions: list[str]
    open_questions: list[str]
    estimated_credits: str = ""


def _criteria(plan: GTMPlan) -> list[IcpCriterion]:
    out: list[IcpCriterion] = []

    def add(
        dimension: str, statement: str, kind: CriterionKind, confidence: str = "medium"
    ) -> None:
        out.append(
            IcpCriterion(
                dimension=dimension,
                statement=statement,
                kind=kind,
                basis="plan",
                confidence=confidence,  # type: ignore[arg-type]
            )
        )

    if plan.countries:
        add("firmographic", f"Headquartered in {', '.join(plan.countries)}", "must_have")
    if plan.employee_ranges:
        add("firmographic", f"{', '.join(plan.employee_ranges)} employees", "must_have")
    if plan.tech_keywords:
        add("technographic", f"Uses {', '.join(plan.tech_keywords)}", "preference")
    for signal in plan.signal_types:
        days = plan.freshness_days.get(signal)
        add("readiness", f"{signal.replace('_', ' ')} within {days} days", "preference")
    if plan.personas:
        titles = ", ".join(p.title for p in plan.personas)
        add("reachability", f"A verified {titles} works there now", "must_have")
    for name in [*plan.excluded_domains, *plan.excluded_names]:
        add("firmographic", f"Is {name}", "disqualifier", "high")
    for key, text in RULES.items():
        if key == "no_fresh_why_now" and not plan.require_fresh_signal:
            continue  # this plan contacts accounts that have no dated reason too
        out.append(
            IcpCriterion(
                dimension="readiness" if "signal" in text else "reachability",
                statement=text,
                kind="disqualifier",
                basis="score_rule",
                confidence="high",
            )
        )
    for dimension, note in plan.dimensions.items():
        out.append(
            IcpCriterion(
                dimension=dimension,
                statement=note,
                kind="context",
                basis="model_inference",
                confidence="low",
            )
        )
    return out


def build_icp(
    plan: GTMPlan,
    mission_id: str,
    plan_id: str,
    version: int,
    author: str,
    rationale: str,
    previous: IcpVersion | None,
    target_hash: str,
    created_at: datetime | None = None,
) -> IcpVersion:
    criteria = _criteria(plan)
    covered = {c.dimension for c in criteria}
    changes: list[str] = []
    if previous is not None:
        now = {c.statement for c in criteria}
        before = {c.statement for c in previous.criteria}
        changes = [f"Added: {s}" for s in sorted(now - before)]
        changes += [f"Removed: {s}" for s in sorted(before - now)]
        if plan.icp_query != previous.icp_query:
            changes.append("Changed the target description")
    return IcpVersion(
        mission_id=mission_id,
        plan_id=plan_id,
        version=version,
        created_at=created_at or datetime.fromtimestamp(0).astimezone(),
        author=author,
        rationale=rationale,
        changes=changes,
        target_hash=target_hash,
        icp_query=plan.icp_query,
        criteria=criteria,
        personas=[{"title": p.title, "function": p.function, "why": p.why} for p in plan.personas],
        gaps=[d for d in DIMENSIONS if d not in covered],
        assumptions=plan.assumptions,
        open_questions=plan.open_questions,
    )
