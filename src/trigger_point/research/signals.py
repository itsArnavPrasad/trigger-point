"""Deterministic why-now signals from provider data. Strength tables are versioned hypotheses."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from trigger_point.mission.models import DEFAULT_FRESHNESS_DAYS, GTMPlan, SignalType
from trigger_point.models.evidence import Evidence, evidence_id
from trigger_point.providers.crustdata.models import Company, JobPosting, SocialPost
from trigger_point.research.posts import employer_matches, keyword_pattern, topic_hits

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
TOPIC_STRENGTH = ((3, 0.9), (2, 0.7), (1, 0.5))  # distinct verified posts
TOPIC_ROLE_BONUS = 0.1  # an author whose title matches a target persona
MAX_POST_EVIDENCE = 3
GENERIC_TITLE_WORDS = frozenset(
    {"senior", "head", "chief", "lead", "assistant", "associate", "and", "the"}
)
FUNDING_STRENGTH = 0.9  # a real, dated event; stronger than an "as of" metric refresh
POSTING_SIGNALS: tuple[SignalType, ...] = ("support_team_growth", "active_hiring")
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
    if "recent_funding" in plan.signal_types and c.funding_last_fundraise_date:
        event_on = _provider_date(c.funding_last_fundraise_date)
        if event_on is not None:
            window = _window(plan, "recent_funding")
            status, age = _status(event_on, window, today)
            amount = f"${c.funding_total_usd:,.0f} " if c.funding_total_usd is not None else ""
            round_type = f"{c.funding_last_round_type} " if c.funding_last_round_type else ""
            claim = (
                f"{c.name or 'The company'} raised a {round_type}round "
                f"{amount}on {event_on.isoformat()} (Crustdata)."
            )
            field_path = "funding.last_fundraise_date"
            ev = Evidence(
                id=evidence_id("account", c.provider_company_id, field_path, event_on),
                entity_type="account",
                entity_id=str(c.provider_company_id),
                claim=claim,
                source_kind="provider_field",
                publisher="Crustdata",
                provider_ref=f"crustdata:{c.source_endpoint}:{field_path}",
                event_on=event_on,
                retrieved_at=c.retrieved_at,
                excerpt=f"{field_path} = {c.funding_last_fundraise_date}",
            )
            evidence.append(ev)
            signals.append(
                Signal(
                    id=evidence_id("signal", c.provider_company_id, "recent_funding", event_on),
                    account_id=c.provider_company_id,
                    type="recent_funding",
                    description=claim,
                    value=c.funding_total_usd,
                    event_on=event_on,
                    as_of=None,
                    age_days=age,
                    window_days=window,
                    status=status,
                    strength=FUNDING_STRENGTH,
                    evidence_ids=[ev.id],
                )
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


def posting_signal(plan: GTMPlan) -> SignalType | None:
    """Which signal a dated posting into the target team evidences on this plan."""
    return next((t for t in POSTING_SIGNALS if t in plan.signal_types), None)


def wants_postings(plan: GTMPlan) -> bool:
    return posting_signal(plan) is not None or bool(plan.tech_keywords)


def signals_from_postings(postings: list[JobPosting], plan: GTMPlan, today: date) -> PostingSignals:
    """Each posting into a persona's function is a dated why-now signal; tech keywords named in
    a posting are fit evidence (the company uses the tool), not timing."""
    out = PostingSignals()
    keywords = persona_keywords(plan)
    signal_type = posting_signal(plan)
    window = _window(plan, signal_type) if signal_type else 0
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
        if signal_type and _matches_title(p.title, keywords):
            out.evidence.append(ev)
            status, age = _status(p.posted_on, window, today)
            out.signals[p.company_id].append(
                Signal(
                    id=evidence_id("signal", p.company_id, signal_type, p.provider_job_id),
                    account_id=p.company_id,
                    type=signal_type,
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


def _title_tokens(title: str | None) -> set[str]:
    words = re.findall(r"[a-z]+", (title or "").casefold())
    return {w for w in words if len(w) >= 4 and w not in GENERIC_TITLE_WORDS}


def _post_excerpt(text: str, keyword: str) -> str:
    text = " ".join(text.split())  # one clean line, whatever the post's own line breaks were
    found = keyword_pattern(keyword).search(text)
    if found is None:
        return text[: 2 * EXCERPT_RADIUS].strip()
    start = max(0, found.start() - EXCERPT_RADIUS)
    return text[start : found.end() + EXCERPT_RADIUS].strip()


def signals_from_posts(
    account: Company, posts: list[SocialPost], plan: GTMPlan, today: date
) -> tuple[list[Signal], list[Evidence]]:
    """People at the account publicly talking about what the seller sells. Every post that counts
    is dated, has a public URL, says the keyword in its own text, and names the account as its
    author's employer. One signal per account, with up to three posts as evidence."""
    kept: list[tuple[SocialPost, list[str]]] = []
    seen: set[str] = set()
    for p in sorted(posts, key=lambda x: x.posted_on or date.min, reverse=True):
        if p.posted_on is None or not p.post_url or p.post_url in seen:
            continue
        if p.post_type not in (None, "original"):
            continue
        hits = topic_hits(p.text, plan.topic_keywords)
        if not employer_matches(account.name, p.author_company) or not hits:
            continue
        seen.add(p.post_url)
        kept.append((p, hits))
    if not kept:
        return [], []

    window = _window(plan, "topic_engagement")
    newest = kept[0][0].posted_on
    assert newest is not None  # noqa: S101 - undated posts were dropped above
    status, age = _status(newest, window, today)
    authors = {p.author_id if p.author_id is not None else p.post_url for p, _ in kept}
    persona_words = {w for persona in plan.personas for w in _title_tokens(persona.title)}
    on_target = any(_title_tokens(p.author_title) & persona_words for p, _ in kept)
    strength = min(
        1.0, _strength(float(len(kept)), TOPIC_STRENGTH) + (TOPIC_ROLE_BONUS if on_target else 0.0)
    )

    evidence: list[Evidence] = []
    for p, hits in kept[:MAX_POST_EVIDENCE]:
        assert p.posted_on is not None and p.post_url is not None  # noqa: S101
        evidence.append(
            Evidence(
                id=evidence_id("post", account.provider_company_id, p.post_url),
                entity_type="account",
                entity_id=str(account.provider_company_id),
                claim=(
                    f"A {p.author_title or 'staff member'} at {p.author_company} posted about "
                    f"{', '.join(hits)} on {p.posted_on.isoformat()} "
                    "(public post; employer matched by name)."
                ),
                source_kind="social_post",
                source_url=p.post_url,
                publisher="Professional network post",
                provider_ref=f"crustdata:{p.source_endpoint}:{p.post_url}",
                event_on=p.posted_on,
                retrieved_at=p.retrieved_at,
                excerpt=_post_excerpt(p.text, hits[0]),
            )
        )
    every_hit = list(dict.fromkeys(h for _, hits in kept for h in hits))
    plural = "" if len(kept) == 1 else "s"
    people = "" if len(authors) == 1 else "s"
    return (
        [
            Signal(
                id=evidence_id("signal", account.provider_company_id, "topic_engagement", newest),
                account_id=account.provider_company_id,
                type="topic_engagement",
                description=(
                    f"{len(kept)} post{plural} by {len(authors)} staff member{people} at "
                    f"{account.name} mention {', '.join(every_hit)}; newest {newest.isoformat()}."
                ),
                value=float(len(kept)),
                event_on=newest,
                as_of=None,
                age_days=age,
                window_days=window,
                status=status,
                strength=strength,
                evidence_ids=[e.id for e in evidence],
            )
        ],
        evidence,
    )
