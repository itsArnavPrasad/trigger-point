"""Deterministic persona matching. A person qualifies only with a verified current employer."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pydantic import BaseModel

from trigger_point.mission.models import GTMPlan
from trigger_point.providers.crustdata.models import (
    PersonCondition,
    PersonConditionGroup,
    PersonRecord,
    PersonSearchRequest,
)
from trigger_point.research.signals import FUNCTION_JOB_KEYWORDS

PEOPLE_VERSION = "people-v1"
SENIORITY_WORDS = (
    "head",
    "director",
    "vp",
    "vice president",
    "chief",
    "lead",
    "manager",
    "senior manager",
)
STOPWORDS = {"of", "and", "the", "&", "for", "/", "-", "e.g."}
EXACT, ALL_WORDS, FUNCTION_SENIORITY = 1.0, 0.8, 0.6
MAX_TITLE_KEYWORDS = 8


class PersonaMatch(BaseModel):
    person: PersonRecord
    persona_title: str
    persona_why: str
    confidence: float
    employer_verified: bool
    reason: str


class RejectedPerson(BaseModel):
    provider_person_id: int
    current_title: str | None
    reason: str  # current_employer_mismatch | not_a_persona_match


@dataclass
class MatchResult:
    matches: list[PersonaMatch] = field(default_factory=list)
    rejected: list[RejectedPerson] = field(default_factory=list)

    @property
    def best(self) -> PersonaMatch | None:
        return self.matches[0] if self.matches else None


def _words(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", text.casefold()) if w and w not in STOPWORDS}


def _has_seniority(title: str) -> bool:
    t = f" {title.casefold()} "
    return any(re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", t) for w in SENIORITY_WORDS)


def _score(title: str, persona_title: str, function: str | None) -> tuple[float, str]:
    t, p = title.casefold(), persona_title.casefold()
    if p in t or t in p:
        return EXACT, f"title matches persona {persona_title!r}"
    if _words(p) and _words(p) <= _words(t):
        return ALL_WORDS, f"title contains every word of persona {persona_title!r}"
    keywords = FUNCTION_JOB_KEYWORDS.get(function or "", ())
    if any(k.strip() in t for k in keywords) and _has_seniority(title):
        return FUNCTION_SENIORITY, f"senior title in the {function} function"
    return 0.0, ""


def match_people(people: list[PersonRecord], account_id: int, plan: GTMPlan) -> MatchResult:
    result = MatchResult()
    for person in people:
        if account_id not in person.current_company_ids:
            result.rejected.append(
                RejectedPerson(
                    provider_person_id=person.provider_person_id,
                    current_title=person.current_title,
                    reason="current_employer_mismatch",
                )
            )
            continue
        titles = [t for t in [person.current_title, *person.current_titles] if t]
        best: tuple[float, str, str, str] = (0.0, "", "", "")
        for persona in plan.personas:
            for title in titles:
                conf, why = _score(title, persona.title, persona.function)
                if conf > best[0]:
                    best = (conf, persona.title, persona.why, why)
        if best[0] == 0:
            result.rejected.append(
                RejectedPerson(
                    provider_person_id=person.provider_person_id,
                    current_title=person.current_title,
                    reason="not_a_persona_match",
                )
            )
            continue
        result.matches.append(
            PersonaMatch(
                person=person,
                persona_title=best[1],
                persona_why=best[2],
                confidence=best[0],
                employer_verified=True,
                reason=best[3],
            )
        )
    result.matches.sort(key=lambda m: (-m.confidence, m.person.provider_person_id))
    return result


def compile_people_request(
    account_ids: list[int], plan: GTMPlan, limit: int
) -> PersonSearchRequest:
    keywords: list[str] = []
    for p in plan.personas:
        for kw in (*FUNCTION_JOB_KEYWORDS.get(p.function or "", ()),):
            kw = kw.strip()
            if kw and kw not in keywords:
                keywords.append(kw)
    keywords = (
        keywords[:MAX_TITLE_KEYWORDS] or [p.title for p in plan.personas][:MAX_TITLE_KEYWORDS]
    )
    title_group = PersonConditionGroup(
        op="or",
        conditions=[
            PersonCondition(
                field="experience.employment_details.current.title", type="(.)", value=k
            )
            for k in keywords
        ],
    )
    return PersonSearchRequest(
        filters=PersonConditionGroup(
            op="and",
            conditions=[
                PersonCondition(
                    field="experience.employment_details.current.company_id",
                    type="in",
                    value=list(account_ids),
                ),
                title_group,
            ],
        ),
        limit=limit,
    )
