"""Deterministic MissionDraft -> GTMPlan -> Crustdata search request.

Every mapping is a table or a rule in this file; anything the LLM proposed that the tables do
not recognise is dropped and recorded as an assumption, never passed through.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from trigger_point.mission.models import (
    DEFAULT_FRESHNESS_DAYS,
    SIGNAL_TYPES,
    GTMPlan,
    MissionDraft,
    PersonaTarget,
    SignalType,
)
from trigger_point.providers.crustdata.client import estimate_search_credits
from trigger_point.providers.crustdata.models import (
    ROLE_FUNCTIONS,
    CompanySearchRequest,
    Condition,
    ConditionGroup,
    SemanticSearch,
)

MAX_ACCOUNTS = 25
# ICP dimensions the model may speak to. The rest come from the plan's own fields.
DIMENSIONS = (
    "operational",
    "problem",
    "value",
    "budget",
    "readiness",
    "buying_process",
    "economics",
)
# Crustdata `locations.country` uses ISO 3166 alpha-3 in the documented example ("USA").
# ASSUMPTION until checked with /company/search/autocomplete on a live key.
_EU = [
    "AUT",
    "BEL",
    "BGR",
    "HRV",
    "CYP",
    "CZE",
    "DNK",
    "EST",
    "FIN",
    "FRA",
    "DEU",
    "GRC",
    "HUN",
    "IRL",
    "ITA",
    "LVA",
    "LTU",
    "LUX",
    "MLT",
    "NLD",
    "POL",
    "PRT",
    "ROU",
    "SVK",
    "SVN",
    "ESP",
    "SWE",
]
COUNTRY_CODES: dict[str, list[str]] = {
    "united states": ["USA"],
    "usa": ["USA"],
    "us": ["USA"],
    "america": ["USA"],
    "canada": ["CAN"],
    "united kingdom": ["GBR"],
    "uk": ["GBR"],
    "great britain": ["GBR"],
    "germany": ["DEU"],
    "france": ["FRA"],
    "netherlands": ["NLD"],
    "ireland": ["IRL"],
    "spain": ["ESP"],
    "italy": ["ITA"],
    "sweden": ["SWE"],
    "denmark": ["DNK"],
    "norway": ["NOR"],
    "finland": ["FIN"],
    "switzerland": ["CHE"],
    "austria": ["AUT"],
    "belgium": ["BEL"],
    "poland": ["POL"],
    "portugal": ["PRT"],
    "australia": ["AUS"],
    "new zealand": ["NZL"],
    "india": ["IND"],
    "singapore": ["SGP"],
    "israel": ["ISR"],
    "japan": ["JPN"],
    "brazil": ["BRA"],
    "mexico": ["MEX"],
    "north america": ["USA", "CAN"],
    "eu": _EU,
    "european union": _EU,
    "europe": [*_EU, "GBR", "CHE", "NOR"],
}
# Crustdata `basic_info.employee_count_range` buckets (professional-network convention).
EMPLOYEE_BUCKETS: list[tuple[str, int, int]] = [
    ("1", 1, 1),
    ("2-10", 2, 10),
    ("11-50", 11, 50),
    ("51-200", 51, 200),
    ("201-500", 201, 500),
    ("501-1000", 501, 1000),
    ("1001-5000", 1001, 5000),
    ("5001-10000", 5001, 10000),
    ("10001+", 10001, 10**9),
]
RESPONSE_FIELDS = ["basic_info", "headcount", "hiring", "locations"]


def _countries(names: list[str], notes: list[str]) -> list[str]:
    out: list[str] = []
    for name in names:
        codes = COUNTRY_CODES.get(name.strip().lower())
        if codes is None:
            notes.append(f"Dropped unrecognised geography {name!r}; add it to the country table.")
            continue
        out.extend(c for c in codes if c not in out)
    return out


_DOMAIN = re.compile(r"\b((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,24})\b", re.IGNORECASE)
_NAME_HEAD = re.compile(r"^([^(:\u2014\u2013,;]+)")
MAX_NAME_WORDS = 4


def _exclusions(items: list[str]) -> tuple[list[str], list[str]]:
    """LLMs write exclusions as prose. Keep every domain mentioned, and a leading company name
    only when it is short enough to be a name rather than a description."""
    domains: set[str] = set()
    names: set[str] = set()
    for item in items:
        domains.update(d.lower() for d in _DOMAIN.findall(item))
        head = _NAME_HEAD.match(item.strip())
        name = head.group(1).strip() if head else ""
        if name and not _DOMAIN.fullmatch(name) and len(name.split()) <= MAX_NAME_WORDS:
            names.add(name)
    return sorted(domains), sorted(names)


MAX_TECH_KEYWORDS = 6


def _tech_keywords(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        kw = " ".join(item.split())[:40]
        if kw and kw.casefold() not in {k.casefold() for k in out}:
            out.append(kw)
    return out[:MAX_TECH_KEYWORDS]


def _employee_ranges(lo: int | None, hi: int | None) -> list[str]:
    """A bucket is included when its midpoint lies inside the requested range."""
    if lo is None and hi is None:
        return []
    low, high = lo or 1, hi or 10**9
    return [name for name, a, b in EMPLOYEE_BUCKETS if low <= (a + min(b, 20000)) / 2 <= high]


def compile_plan(draft: MissionDraft, seller_domain: str, credit_budget: float) -> GTMPlan:
    notes: list[str] = list(draft.assumptions)
    signals: list[SignalType] = []
    for s in draft.signal_types:
        if s in SIGNAL_TYPES and s not in signals:
            signals.append(s)  # type: ignore[arg-type]
        elif s not in SIGNAL_TYPES:
            notes.append(f"Dropped unsupported signal type {s!r}.")
    personas = []
    for p in draft.personas:
        fn = p.function if p.function in ROLE_FUNCTIONS else None
        if fn is None:
            notes.append(f"Persona {p.title!r}: unknown role function {p.function!r} ignored.")
        personas.append(PersonaTarget(title=p.title, function=fn, why=p.why))
    max_accounts = max(1, draft.max_accounts)
    if max_accounts > MAX_ACCOUNTS:
        notes.append(f"max_accounts {max_accounts} capped at {MAX_ACCOUNTS} for the MVP.")
        max_accounts = MAX_ACCOUNTS
    domains, names = _exclusions(draft.exclusions)
    domains = sorted({seller_domain.lower(), *domains})
    return GTMPlan(
        icp_query=draft.icp_query.strip(),
        countries=_countries(draft.countries, notes),
        employee_ranges=_employee_ranges(draft.employee_min, draft.employee_max),
        personas=personas,
        signal_types=signals,
        excluded_domains=domains,
        excluded_names=names,
        tech_keywords=_tech_keywords(draft.tech_keywords),
        max_accounts=max_accounts,
        credit_budget=credit_budget,
        freshness_days={s: DEFAULT_FRESHNESS_DAYS[s] for s in signals},
        assumptions=notes,
        open_questions=draft.open_questions[:3],
        dimensions={
            k: v.strip() for k, v in draft.dimensions.items() if k in DIMENSIONS and v.strip()
        },
    )


def compile_search_request(plan: GTMPlan) -> CompanySearchRequest:
    conditions: list[Condition | ConditionGroup] = []
    if plan.countries:
        conditions.append(
            Condition(field="locations.country", type="in", value=list(plan.countries))
        )
    if plan.employee_ranges:
        conditions.append(
            Condition(
                field="basic_info.employee_count_range", type="in", value=list(plan.employee_ranges)
            )
        )
    filters: Condition | ConditionGroup | None = None
    if len(conditions) == 1:
        filters = conditions[0]
    elif conditions:
        filters = ConditionGroup(op="and", conditions=conditions)
    probe = CompanySearchRequest(
        search=SemanticSearch(query=plan.icp_query),
        filters=filters,
        fields=RESPONSE_FIELDS,
        limit=1,
    )
    per_result = estimate_search_credits(probe)
    affordable = int(Decimal(str(plan.credit_budget)) / per_result)
    if affordable < 1:
        raise ValueError(
            f"credit budget {plan.credit_budget} cannot afford one result "
            f"({per_result} credits each)"
        )
    limit = min(100, 3 * plan.max_accounts, affordable)
    return probe.model_copy(update={"limit": limit})


@dataclass(frozen=True)
class RelaxationStep:
    description: str
    plan: GTMPlan


def relaxation_steps(plan: GTMPlan) -> list[RelaxationStep]:
    """Cumulative, one constraint at a time: size first, then geography."""
    steps: list[RelaxationStep] = []
    current = plan
    if current.employee_ranges:
        current = current.model_copy(update={"employee_ranges": []})
        steps.append(RelaxationStep("drop company-size filter", current))
    if current.countries:
        current = current.model_copy(update={"countries": []})
        steps.append(RelaxationStep("drop country filter", current))
    return steps
