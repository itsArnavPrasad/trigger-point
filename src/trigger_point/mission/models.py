"""GTM mission: the LLM proposes a MissionDraft; deterministic code compiles a GTMPlan."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from trigger_point.models.context import RunMode

SignalType = Literal[
    "support_team_growth", "headcount_growth", "active_hiring", "recent_funding", "topic_engagement"
]
SIGNAL_TYPES: tuple[str, ...] = (
    "support_team_growth",
    "headcount_growth",
    "active_hiring",
    "recent_funding",
    "topic_engagement",
)
# Starting freshness policy (docs/EVIDENCE_AND_VERIFICATION.md); configurable assumptions.
DEFAULT_FRESHNESS_DAYS: dict[str, int] = {
    "recent_funding": 90,
    "topic_engagement": 120,  # a dated public post by someone at the account
    # Metric signals are aged from the provider's as-of date; the policy caps hooks at 120 days.
    "active_hiring": 120,
    "headcount_growth": 120,
    "support_team_growth": 30,  # evidenced by dated job postings into the target team
}


class PersonaDraft(BaseModel):
    title: str
    function: str
    why: str


class MissionDraft(BaseModel):
    """Wire schema for the mission-compile LLM step."""

    icp_query: str
    countries: list[str]
    employee_min: int | None
    employee_max: int | None
    personas: list[PersonaDraft]
    signal_types: list[str]
    exclusions: list[str]
    max_accounts: int
    assumptions: list[str]
    open_questions: list[str]
    tech_keywords: list[str] = Field(default_factory=list)
    topic_keywords: list[str]  # required on purpose: a model may skip an optional field
    industries: list[str]  # required for the same reason; empty is a valid answer
    places: list[str]
    dimensions: dict[str, str] = Field(default_factory=dict)


class PersonaTarget(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    function: str | None  # a Crustdata role function, or None if the LLM's value was unknown
    why: str


class GTMPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    icp_query: str = Field(min_length=1, max_length=2000)
    countries: list[str] = Field(default_factory=list)  # Crustdata locations.country values
    employee_ranges: list[str] = Field(default_factory=list)
    personas: list[PersonaTarget] = Field(default_factory=list)
    signal_types: list[SignalType] = Field(default_factory=list)
    excluded_domains: list[str] = Field(default_factory=list)
    excluded_names: list[str] = Field(default_factory=list)
    tech_keywords: list[str] = Field(default_factory=list)
    topic_keywords: list[str] = Field(default_factory=list)  # what staff would post about if open
    industries: list[str] = Field(default_factory=list)  # Crustdata industry names
    places: list[str] = Field(default_factory=list)  # words in a headquarters address
    # True: an account with no dated reason to act now is rejected. False: it is still ranked,
    # people-searched and contactable, and its missing reason stays visible.
    require_fresh_signal: bool = True
    max_accounts: int = Field(ge=1, le=25)
    credit_budget: float = Field(gt=0)
    freshness_days: dict[str, int] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    dimensions: dict[str, str] = Field(default_factory=dict)


MissionStatus = Literal["review_required", "approved"]


class Mission(BaseModel):
    id: str
    context_id: str
    context_version: int
    user_goal: str
    plan: GTMPlan
    search_request: dict[str, object]  # compiled Crustdata body, exactly what will be sent
    estimated_credits: str
    status: MissionStatus = "review_required"
    mode: RunMode
    llm_mode: str
    created_at: datetime
    initiated_by: str = "ui"
    approved_at: datetime | None = None
