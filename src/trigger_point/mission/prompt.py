"""Mission-compile prompt. The approved context is seller-reviewed but still escaped as data."""

from __future__ import annotations

import html

from trigger_point.mission.models import SIGNAL_TYPES
from trigger_point.models.context import CLAIM_LIST_FIELDS, BusinessContext
from trigger_point.providers.crustdata.models import ROLE_FUNCTIONS

PROMPT_VERSION = "mission-prompt-v1"

MISSION_SYSTEM_PROMPT = f"""\
You turn a seller's approved business context and revenue goal into a target-market hypothesis \
for B2B account research. Code validates and compiles your answer; anything outside the allowed \
values is dropped.

Fields:
- icp_query: one or two sentences describing the companies to find, written for a semantic \
company search (what they do, who they sell to, what situation makes the seller relevant).
- countries: plain country or region names (e.g. "United States", "Europe"). Empty if unknown.
- employee_min / employee_max: company size in employees, or null if the context does not say.
- personas: the people who own the problem, not by default the CEO. function must be one of: \
{", ".join(ROLE_FUNCTIONS)}.
- signal_types: observable reasons to act now, chosen only from: {", ".join(SIGNAL_TYPES)}.
- exclusions: companies that must not be targeted (competitors, partners the seller depends \
on, existing customers named in the context). One company per item, written as \
"Name (domain.com)" when the domain is known; no explanations.
- tech_keywords: up to 6 product names the seller integrates with or replaces, exactly as \
written in the context (e.g. "Zendesk"). Job postings that name them are evidence of fit.
- dimensions: what the context says about any of these ICP dimensions: operational, problem, \
value, budget, readiness, buying_process, economics. One short sentence each. Leave a dimension \
out when the context does not support it; never guess.
- max_accounts: how many accounts to research (at most 25).
- assumptions: every choice you made that the context does not state.
- open_questions: at most 3 questions whose answers would change the targeting.

Use only the context provided. Items marked [inference] are hypotheses, not facts.
"""


def build_mission_message(ctx: BusinessContext) -> str:
    lines = [
        f"Seller: {html.escape(ctx.company_name.text if ctx.company_name else ctx.domain)}",
        f"Seller domain: {ctx.domain}",
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
