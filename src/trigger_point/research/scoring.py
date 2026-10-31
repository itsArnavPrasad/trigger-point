"""Deterministic, versioned account scoring. The LLM never computes or adjusts a score.

score-v1 is a starting hypothesis (docs/EVIDENCE_AND_VERIFICATION.md), not a calibrated
probability. Unknown components contribute 0 and reduce `coverage`; nothing is imputed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from trigger_point.mission.models import GTMPlan
from trigger_point.providers.crustdata.models import Company
from trigger_point.research.signals import Signal

SCORE_VERSION = "score-v1"
WEIGHTS = {"fit": 0.35, "timing": 0.35, "reachability": 0.20, "evidence_quality": 0.10}
TIER_THRESHOLDS = (("A", 70.0), ("B", 50.0))
DATED_EVENT_QUALITY, AS_OF_METRIC_QUALITY = 1.0, 0.7
ScoreStatus = Literal["qualified", "insufficient_evidence", "rejected"]


class Component(BaseModel):
    value: float | None  # 0-100, None when unknown
    known: bool
    detail: str


class ScoreBreakdown(BaseModel):
    version: str = SCORE_VERSION
    total: float
    coverage: float
    components: dict[str, Component]
    rejections: list[str]
    status: ScoreStatus
    tier: str | None


@dataclass(frozen=True)
class PeopleOutcome:
    searched: bool
    best_match_confidence: float | None = None  # 0-1 for the best verified persona match


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def _fit(c: Company, plan: GTMPlan, tech_hits: int) -> Component:
    parts: list[tuple[str, float]] = []
    notes: list[str] = []
    if plan.countries:
        if c.hq_country:
            ok = c.hq_country in plan.countries
            parts.append(("geography", 100.0 if ok else 0.0))
            notes.append(f"geography {c.hq_country} {'in' if ok else 'not in'} plan")
        else:
            notes.append("geography unknown")
    if plan.employee_ranges:
        if c.employee_count_range:
            ok = c.employee_count_range in plan.employee_ranges
            parts.append(("size", 100.0 if ok else 0.0))
            notes.append(f"size {c.employee_count_range} {'in' if ok else 'not in'} plan")
        else:
            notes.append("size unknown")
    if plan.tech_keywords:
        if tech_hits:
            parts.append(("tech", 100.0))
            notes.append(f"tech: {tech_hits} job posting(s) name a seller integration")
        else:
            notes.append("tech fit unknown (no posting names a seller integration)")
    if not parts:
        return Component(value=None, known=False, detail="; ".join(notes) or "no fit criteria")
    return Component(
        value=_clamp(sum(v for _, v in parts) / len(parts)), known=True, detail="; ".join(notes)
    )


def _active(signals: list[Signal]) -> list[Signal]:
    return [s for s in signals if s.status == "active" and s.age_days is not None]


def _timing(signals: list[Signal], collected: bool) -> Component:
    if not collected:
        return Component(value=None, known=False, detail="signals not collected")
    active = _active(signals)
    remaining = 1.0
    for s in active:
        tau = max(s.window_days / 2, 1.0)
        remaining *= 1 - s.strength * math.exp(-(s.age_days or 0) / tau)
    expired = sum(1 for s in signals if s.status == "expired")
    undated = sum(1 for s in signals if s.status == "undated")
    return Component(
        value=_clamp(100 * (1 - remaining)),
        known=True,
        detail=f"{len(active)} active signal(s); {expired} expired, {undated} undated (not used)",
    )


def _reachability(people: PeopleOutcome) -> Component:
    if not people.searched:
        return Component(value=None, known=False, detail="people not searched (budget or stage)")
    if people.best_match_confidence is None:
        return Component(value=0.0, known=True, detail="no verified persona match found")
    return Component(
        value=_clamp(100 * people.best_match_confidence),
        known=True,
        detail=f"best verified persona match confidence {people.best_match_confidence}",
    )


def _evidence_quality(signals: list[Signal]) -> Component:
    active = _active(signals)
    if not active:
        return Component(value=0.0, known=True, detail="no active signal evidence")
    q = [DATED_EVENT_QUALITY if s.event_on else AS_OF_METRIC_QUALITY for s in active]
    return Component(
        value=_clamp(100 * sum(q) / len(q)),
        known=True,
        detail=f"{sum(1 for s in active if s.event_on)} dated event(s), "
        f"{sum(1 for s in active if not s.event_on)} as-of metric(s)",
    )


def score_account(
    company: Company,
    signals: list[Signal],
    tech_hits: int,
    people: PeopleOutcome,
    plan: GTMPlan,
    signals_collected: bool,
) -> ScoreBreakdown:
    components = {
        "fit": _fit(company, plan, tech_hits),
        "timing": _timing(signals, signals_collected),
        "reachability": _reachability(people),
        "evidence_quality": _evidence_quality(signals),
    }
    total = round(sum(WEIGHTS[k] * (c.value or 0.0) for k, c in components.items() if c.known), 2)
    coverage = round(sum(WEIGHTS[k] for k, c in components.items() if c.known), 4)
    rejections: list[str] = []
    if not company.primary_domain:
        rejections.append("identity_unresolved")
    if plan.require_fresh_signal and components["timing"].known and components["timing"].value == 0:
        rejections.append("no_fresh_why_now")
    if components["reachability"].known and components["reachability"].value == 0:
        rejections.append("no_relevant_buyer")
    status: ScoreStatus = (
        "rejected" if rejections else "insufficient_evidence" if coverage < 1 else "qualified"
    )
    tier = None
    if status == "qualified":
        tier = next((t for t, threshold in TIER_THRESHOLDS if total >= threshold), "C")
    return ScoreBreakdown(
        total=total,
        coverage=coverage,
        components=components,
        rejections=rejections,
        status=status,
        tier=tier,
    )


def rank(items: list[tuple[int, ScoreBreakdown]]) -> list[tuple[int, ScoreBreakdown]]:
    """Total desc, then timing desc, then provider id asc: identical inputs, identical order."""
    return sorted(
        items, key=lambda x: (-x[1].total, -(x[1].components["timing"].value or 0.0), x[0])
    )
