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


MAX_KEYWORDS = 6


MAX_INDUSTRIES = 5
MAX_PLACES = 4


def _keywords(items: list[str], limit: int = MAX_KEYWORDS, width: int = 40) -> list[str]:
    out: list[str] = []
    for item in items:
        kw = " ".join(item.split())[:width]
        if kw and kw.casefold() not in {k.casefold() for k in out}:
            out.append(kw)
    return out[:limit]


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.casefold())


def _topic_keywords(items: list[str], icp_query: str, notes: list[str]) -> list[str]:
    """Topics that show openness to change. A word that is part of how the buyer is described
    ("CBSE", "schools") matches nearly everything the buyer posts, so it shows nothing."""
    described = set(_words(icp_query))
    kept: list[str] = []
    for kw in _keywords(items, limit=10**6):
        words = _words(kw)
        if words and all(w in described for w in words):
            notes.append(
                f"Dropped topic keyword {kw!r}: it describes the buyer, so it cannot show "
                "openness to change."
            )
        else:
            kept.append(kw)
    return kept[:MAX_KEYWORDS]


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
    topic_keywords = _topic_keywords(draft.topic_keywords, draft.icp_query, notes)
    if "topic_engagement" in signals and not topic_keywords:
        signals.remove("topic_engagement")
        notes.append(
            "Dropped signal type 'topic_engagement': it searches public posts for topic "
            "keywords, and none were given."
        )
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
        tech_keywords=_keywords(draft.tech_keywords),
        topic_keywords=topic_keywords,
        industries=_keywords(draft.industries, limit=MAX_INDUSTRIES, width=60),
        places=_keywords(draft.places, limit=MAX_PLACES, width=60),
        max_accounts=max_accounts,
        require_fresh_signal=False,
        credit_budget=credit_budget,
        freshness_days={s: DEFAULT_FRESHNESS_DAYS[s] for s in signals},
        assumptions=[
            *notes,
            "Accounts with no dated reason to act now are still ranked and contacted. The missing "
            "reason is shown, never invented.",
        ],
        open_questions=draft.open_questions[:3],
        dimensions={
            k: v.strip() for k, v in draft.dimensions.items() if k in DIMENSIONS and v.strip()
        },
    )


def favour_signals(plan: GTMPlan, favoured: list[str]) -> GTMPlan:
    """What a person approved after seeing real outcomes: these signals led to meetings. They are
    added in code, not suggested to the model, and the plan says so. A topic signal still needs
    topic keywords to search with."""
    signals = list(plan.signal_types)
    notes = list(plan.assumptions)
    freshness = dict(plan.freshness_days)
    for name in dict.fromkeys(favoured):
        if name not in SIGNAL_TYPES or name in signals:
            continue
        if name == "topic_engagement" and not plan.topic_keywords:
            notes.append(
                "An approved lesson favoured 'topic_engagement', but it has no topic keywords to "
                "search with, so it was not added."
            )
            continue
        signals.append(name)  # type: ignore[arg-type]
        freshness[name] = DEFAULT_FRESHNESS_DAYS[name]
        notes.append(
            f"Added signal type {name!r}: an approved lesson, learned from real outcomes, "
            "favoured it."
        )
    return plan.model_copy(
        update={"signal_types": signals, "assumptions": notes, "freshness_days": freshness}
    )


def response_fields(plan: GTMPlan) -> list[str]:
    """`funding` is a premium field group, billed per result received, so it is requested only
    when the plan actually wants a funding signal."""
    fields = list(RESPONSE_FIELDS)
    if "recent_funding" in plan.signal_types:
        fields.append("funding")
    return fields


_DETAIL = re.compile(r"\s+(?:with|that|which|who|using|teaching|offering|where|whose|having)\b")
_SEGMENTS = ("school", "college", "university", "hospital", "clinic")


def buyer_query(query: str) -> str:
    """The search names the kind of organisation and where, nothing about what they do.
    "CBSE schools in India with students in Classes 6 to 10 that teach maths" finds tutoring
    apps; "CBSE schools in India" finds schools. Only cut when a buyer segment word survives."""
    head = _DETAIL.split(query.strip(), maxsplit=1)[0].strip(" ,.")
    return head if any(w in head.casefold() for w in _SEGMENTS) else query.strip()


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
    if plan.industries:
        conditions.append(
            Condition(field="basic_info.industries", type="in", value=list(plan.industries))
        )
    if plan.places:
        where: list[Condition | ConditionGroup] = [
            Condition(field="locations.headquarters", type="(.)", value=p) for p in plan.places
        ]
        conditions.append(
            where[0] if len(where) == 1 else ConditionGroup(op="or", conditions=where)
        )
    filters: Condition | ConditionGroup | None = None
    if len(conditions) == 1:
        filters = conditions[0]
    elif conditions:
        filters = ConditionGroup(op="and", conditions=conditions)
    probe = CompanySearchRequest(
        search=SemanticSearch(query=buyer_query(plan.icp_query)),
        filters=filters,
        fields=response_fields(plan),
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
    """Cumulative, one constraint at a time: size, then the loosest text filters, then country."""
    steps: list[RelaxationStep] = []
    current = plan
    if current.employee_ranges:
        current = current.model_copy(update={"employee_ranges": []})
        steps.append(RelaxationStep("drop company-size filter", current))
    while current.places and all(p.count(",") >= 2 for p in current.places):
        # "Powai, Mumbai, Maharashtra, India" -> "Mumbai, Maharashtra, India": the neighbourhood is
        # what a record rarely says, the city is what it usually does.
        wider = [p.split(",", 1)[1].strip() for p in current.places]
        current = current.model_copy(update={"places": list(dict.fromkeys(wider))})
        steps.append(RelaxationStep(f"widen place to {'; '.join(current.places)}", current))
    if current.places:
        current = current.model_copy(update={"places": []})
        steps.append(RelaxationStep("drop place filter", current))
    if current.industries:
        current = current.model_copy(update={"industries": []})
        steps.append(RelaxationStep("drop industry filter", current))
    if current.countries:
        current = current.model_copy(update={"countries": []})
        steps.append(RelaxationStep("drop country filter", current))
    return steps
