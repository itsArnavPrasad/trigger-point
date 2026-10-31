"""Deterministic why-now signals from provider data. Strength tables are versioned hypotheses."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from trigger_point.mission.models import DEFAULT_FRESHNESS_DAYS, GTMPlan
from trigger_point.models.evidence import Evidence, evidence_id
from trigger_point.providers.crustdata.models import Company, JobPosting

SIGNALS_VERSION = "signals-v1"
SignalStatus = Literal["active", "expired", "undated"]

# Job-title keywords that indicate hiring into a persona's function (the team the seller helps).
FUNCTION_JOB_KEYWORDS: dict[str, tuple[str, ...]] = {
    "customer_success_and_support": (
        "support",
        "customer success",
        "customer experience",
        "help desk",
        "helpdesk",
        "customer care",
        "customer service",
    ),
    "education": ("teacher", "academic", "curriculum", "principal", "faculty", "digital learning"),
    "sales": ("sales", "account executive", "sales development", "business development rep"),
    "marketing": ("marketing", "demand generation", "growth marketing", "content marketing"),
    "engineering": ("engineer", "developer", "sre", "devops"),
    "information_technology": ("it ", "systems administrator", "it support", "infrastructure"),
    "operations": ("operations", "revops", "revenue operations"),
    "finance": ("finance", "accountant", "controller", "fp&a"),
    "human_resources": ("recruiter", "people partner", "hr ", "talent"),
    "legal": ("legal", "counsel", "compliance", "privacy"),
    "product_management": ("product manager", "product owner"),
    "business_development": ("business development", "partnerships"),
}
GROWTH_STRENGTH = ((20.0, 1.0), (10.0, 0.7), (5.0, 0.4))  # 6-month headcount growth %
OPENINGS_STRENGTH = ((20, 0.8), (10, 0.6), (3, 0.4))  # open roles
FUNCTION_POSTING_STRENGTH = 0.6
EXCERPT_RADIUS = 80


class Signal(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    account_id: int
    type: str
    description: str
    value: float | None
    event_on: date | None
    as_of: date | None
    age_days: int | None
    window_days: int
    status: SignalStatus
    strength: float
    evidence_ids: list[str]
    version: str = SIGNALS_VERSION


def _status(reference: date | None, window: int, today: date) -> tuple[SignalStatus, int | None]:
    if reference is None:
        return "undated", None
    age = (today - reference).days
    return ("expired" if age > window else "active"), age


def _strength(value: float, table: tuple[tuple[float, float], ...]) -> float:
    return next((s for threshold, s in table if value >= threshold), 0.0)


def _provider_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _window(plan: GTMPlan, kind: str) -> int:
    return plan.freshness_days.get(kind, DEFAULT_FRESHNESS_DAYS[kind])


def signals_from_company(
    c: Company, plan: GTMPlan, today: date
) -> tuple[list[Signal], list[Evidence]]:
    """Metric signals are 'as of' the provider's last refresh; they have no event date."""
    as_of = _provider_date(c.provider_updated_at)
    as_of_text = f"as of {as_of.isoformat()}" if as_of else "provider refresh date unknown"
    signals: list[Signal] = []
    evidence: list[Evidence] = []

    def add(kind: str, value: float, strength: float, claim: str, field_path: str) -> None:
        window = _window(plan, kind)
        status, age = _status(as_of, window, today)
        ev = Evidence(
            id=evidence_id("account", c.provider_company_id, field_path, value, as_of),
            entity_type="account",
            entity_id=str(c.provider_company_id),
            claim=claim,
            source_kind="provider_field",
            publisher="Crustdata",
            provider_ref=f"crustdata:{c.source_endpoint}:{field_path}",
            as_of=as_of,
            retrieved_at=c.retrieved_at,
            excerpt=f"{field_path} = {value}",
        )
        evidence.append(ev)
        signals.append(
            Signal(
                id=evidence_id("signal", c.provider_company_id, kind, field_path, as_of),
                account_id=c.provider_company_id,
                type=kind,
                description=claim,
                value=value,
                event_on=None,
                as_of=as_of,
                age_days=age,
                window_days=window,
                status=status,
                strength=strength,
                evidence_ids=[ev.id],
            )
        )

    g = c.headcount_growth_6m_pct
    if "headcount_growth" in plan.signal_types and g is not None:
        strength = _strength(g, GROWTH_STRENGTH)
        if strength:
            add(
                "headcount_growth",
                g,
                strength,
                f"{c.name or 'The company'} headcount grew {g}% over 6 months ({as_of_text}, "
                f"Crustdata).",
                "headcount.growth_percent.6m",
            )
    n = c.hiring_openings
    if "active_hiring" in plan.signal_types and n is not None:
        strength = _strength(float(n), OPENINGS_STRENGTH)
        if strength:
            add(
                "active_hiring",
                float(n),
                strength,
                f"{c.name or 'The company'} had {n} open roles ({as_of_text}, Crustdata).",
                "hiring.openings_count",
            )
    return signals, evidence


@dataclass
class PostingSignals:
    signals: dict[int, list[Signal]] = field(default_factory=lambda: defaultdict(list))
    tech_evidence: dict[int, list[Evidence]] = field(default_factory=lambda: defaultdict(list))
    evidence: list[Evidence] = field(default_factory=list)


def persona_keywords(plan: GTMPlan) -> list[str]:
    seen: list[str] = []
    for p in plan.personas:
        for kw in FUNCTION_JOB_KEYWORDS.get(p.function or "", ()):
            if kw not in seen:
                seen.append(kw)
    return seen


def _matches_title(title: str, keywords: list[str]) -> bool:
    t = f" {title.casefold()} "
    return any(kw in t for kw in keywords)


def _excerpt(text: str, start: int, end: int) -> str:
    a, b = max(0, start - EXCERPT_RADIUS), min(len(text), end + EXCERPT_RADIUS)
    return ("…" if a else "") + text[a:b].strip() + ("…" if b < len(text) else "")


def signals_from_postings(postings: list[JobPosting], plan: GTMPlan, today: date) -> PostingSignals:
    """Each posting into a persona's function is a dated why-now signal; tech keywords named in
    a posting are fit evidence (the company uses the tool), not timing."""
    out = PostingSignals()
    keywords = persona_keywords(plan)
    window = _window(plan, "support_team_growth")
    seen: set[tuple[int, object]] = set()
    tech_seen: set[tuple[int, str]] = set()
    for p in postings:
        if p.company_id is None or not p.title:
            continue
        key = (p.company_id, p.provider_job_id or p.url or p.title)
        if key in seen:
            continue
        seen.add(key)
        dates = f"posted {p.posted_on.isoformat()}" if p.posted_on else "posting date unknown"
        if p.last_seen_on:
            dates += f", last seen {p.last_seen_on.isoformat()}"
        ev = Evidence(
            id=evidence_id("job", p.company_id, p.provider_job_id, p.url, p.posted_on),
            entity_type="account",
            entity_id=str(p.company_id),
            claim=f"Job posting: {p.title!r} ({dates}).",
            source_kind="job_posting",
            source_url=p.url,
            publisher="Crustdata job index",
            provider_ref=f"crustdata:/job/search:{p.provider_job_id}",
            event_on=p.posted_on,
            as_of=p.last_seen_on,
            retrieved_at=p.retrieved_at,
            excerpt=p.title,
        )
        relevant = "support_team_growth" in plan.signal_types and _matches_title(p.title, keywords)
        if relevant:
            out.evidence.append(ev)
            status, age = _status(p.posted_on, window, today)
            out.signals[p.company_id].append(
                Signal(
                    id=evidence_id(
                        "signal", p.company_id, "support_team_growth", p.provider_job_id
                    ),
                    account_id=p.company_id,
                    type="support_team_growth",
                    description=f"Hiring into the target team: {p.title} ({dates}).",
                    value=None,
                    event_on=p.posted_on,
                    as_of=p.last_seen_on,
                    age_days=age,
                    window_days=window,
                    status=status,
                    strength=FUNCTION_POSTING_STRENGTH,
                    evidence_ids=[ev.id],
                )
            )
        for kw in plan.tech_keywords:
            if (p.company_id, kw.casefold()) in tech_seen or not p.description:
                continue
            m = re.search(rf"(?<![\w]){re.escape(kw)}(?![\w])", p.description, re.IGNORECASE)
            if m:
                tech_seen.add((p.company_id, kw.casefold()))
                tech = Evidence(
                    id=evidence_id("tech", p.company_id, kw, p.provider_job_id),
                    entity_type="account",
                    entity_id=str(p.company_id),
                    claim=f"A job posting ({p.title!r}, {dates}) mentions {kw}.",
                    source_kind="job_posting",
                    source_url=p.url,
                    publisher="Crustdata job index",
                    provider_ref=f"crustdata:/job/search:{p.provider_job_id}:content.description",
                    event_on=p.posted_on,
                    as_of=p.last_seen_on,
                    retrieved_at=p.retrieved_at,
                    excerpt=_excerpt(p.description, m.start(), m.end()),
                )
                out.tech_evidence[p.company_id].append(tech)
                out.evidence.append(tech)
    return out
