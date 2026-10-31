"""GTM strategy step: market, value proposition, positioning, motion and channels.

The model proposes; code labels. Everything is a hypothesis until a person approves it. A
competitor counts as observed only if the approved profile names it, and proof must be a proof
point the seller approved, otherwise it moves to the list of claims that need proof."""

from __future__ import annotations

import html
from typing import Literal

from pydantic import BaseModel

from trigger_point.models.context import CLAIM_LIST_FIELDS, BusinessContext

PROMPT_VERSION = "strategy-prompt-v1"
Availability = Literal["draft_only", "manual"]

SYSTEM_PROMPT = """\
You draft a go-to-market strategy for a seller from their approved business context. A person \
reviews it, and code checks it. Everything you write is a hypothesis.

Rules:
- Use only the context provided. Never invent customers, metrics, revenue, conversion rates or \
private tactics of any company. Use empty strings or lists rather than guessing.
- competitors: type is direct, indirect, substitute or status_quo. Include what buyers do today. \
basis is "stated" only if the context names it, otherwise "inferred".
- value_proposition.proof: only a proof point from the context, copied exactly, otherwise "".
- customer_language: how the buyer would say it, not product language.
- capability_outcomes: map a capability to what the customer gets. Do not restate features.
- gtm_motion: the simplest motion that fits, from founder-led sales, outbound, inbound, \
product-led, partnerships, community, content, events, channel sales or a hybrid. Say why, and \
why the alternatives were rejected. If the buyers are consumers, say so plainly.
- claims_needing_proof: claims that would need customer proof or legal review.
- experiments: a hypothesis, what varies, the metric and a decision rule.
- open_questions: at most 3, only where the answer would change the strategy.
"""


class Competitor(BaseModel):
    name: str
    type: str
    basis: Literal["stated", "inferred"]


class ValueProposition(BaseModel):
    target_segment: str
    problem: str
    current_alternative: str
    outcome: str
    differentiation: str
    proof: str
    customer_language: str


class CapabilityOutcome(BaseModel):
    capability: str
    outcome: str


class Pillar(BaseModel):
    pillar: str
    proof: str


class StakeholderMessage(BaseModel):
    role: str
    message: str


class Motion(BaseModel):
    motion: str
    why: str
    alternatives_rejected: list[str]


class Channel(BaseModel):
    channel: str
    audience: str
    purpose: str
    offer: str
    timing: str
    owner: str
    success_metric: str
    availability: Availability = "manual"


class Experiment(BaseModel):
    hypothesis: str
    variant: str
    metric: str
    decision_rule: str


class StrategyDraft(BaseModel):
    market_category: str
    adjacent_categories: list[str]
    competitors: list[Competitor]
    market_gaps: list[str]
    differentiation_hypotheses: list[str]
    value_proposition: ValueProposition
    capability_outcomes: list[CapabilityOutcome]
    positioning: str
    message_pillars: list[Pillar]
    stakeholder_messages: list[StakeholderMessage]
    claims_needing_proof: list[str]
    gtm_motion: Motion
    channels: list[Channel]
    experiments: list[Experiment]
    open_questions: list[str]


def build_strategy_message(ctx: BusinessContext) -> str:
    lines = [
        f"Seller: {html.escape(ctx.company_name.text if ctx.company_name else ctx.domain)}",
        f"<seller_goal>\n{html.escape(ctx.user_goal, quote=False)}\n</seller_goal>",
        f"Stated target geography: {html.escape(ctx.target_geography or 'not stated')}",
        f"Stated time horizon: {html.escape(ctx.time_horizon or 'not stated')}",
        "<approved_context>",
    ]
    for name in CLAIM_LIST_FIELDS:
        items = getattr(ctx, name)
        if items:
            lines.append(f"{name}:")
            lines.extend(f"- [{c.kind}] {html.escape(c.text, quote=False)}" for c in items)
    lines.append("</approved_context>")
    return "\n".join(lines)
