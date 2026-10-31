"""Mission-compile prompt. The approved context is seller-reviewed but still escaped as data."""

from __future__ import annotations

import html

from trigger_point.mission.models import SIGNAL_TYPES
from trigger_point.models.context import CLAIM_LIST_FIELDS, BusinessContext
from trigger_point.providers.crustdata.models import ROLE_FUNCTIONS

PROMPT_VERSION = "mission-prompt-v5"

MISSION_SYSTEM_PROMPT = f"""\
You turn a seller's approved business context and revenue goal into a target-market hypothesis \
for B2B account research. Code validates and compiles your answer; anything outside the allowed \
values is dropped.

Choose buyers who can adopt and pay, not merely buyers that exist. When the seller's product is \
a paid learning product for students (an AI tutor, a learning platform), prefer well-resourced, \
premium institutions that value outcomes and can spend time and money on a pilot: private fee-paying \
schools in major cities, and international-curriculum schools (IB, IGCSE, Cambridge) or well-known \
CBSE and ICSE schools with strong fees, never government schools, tiny village schools or \
coaching shops. Examples of good icp_query lines for that seller: "Premium private CBSE and \
ICSE schools in Mumbai, Delhi NCR and Bengaluru", "International IB and IGCSE schools in \
India", "High-fee private K-12 schools in Hyderabad and Pune". Use the same thinking for \
other sellers: aim at the segment with budget, urgency and a named decision maker. For \
schools the personas are the Principal, the Head of Academics or Curriculum, the Maths \
Coordinator and the Director or Trustee, in that order of reach.

Fields:
- icp_query: one sentence describing the buyer organisations to find, for a semantic company \
search: what kind of organisation they are, what they do and where. Describe only the buyer. \
Never mention the seller, its product or its category, because a search for those words finds \
competitors. A seller of an AI maths tutor to schools searches for "CBSE schools in Mumbai", \
not for "schools that could use an AI maths tutor".
- countries: plain country or region names (e.g. "United States", "Europe"). Empty if unknown.
- employee_min / employee_max: company size in employees, or null if the context does not say.
- personas: the people who own the problem, not by default the CEO. function must be one of: \
{", ".join(ROLE_FUNCTIONS)}.
- signal_types: observable, dated reasons to act now, chosen only from: {", ".join(SIGNAL_TYPES)}. \
Each comes from a specific Crustdata source and only fires if that source actually has data for \
this kind of buyer:
  - support_team_growth, active_hiring: a dated job posting into the relevant team. Needs a buyer \
that posts roles on channels Crustdata indexes (mainly venture-backed or larger companies). \
Schools, government bodies, small local businesses and most consumer-facing organisations \
usually post nothing Crustdata can see.
  - headcount_growth: an employee-count trend as of Crustdata's last refresh. Same coverage limit \
as above; needs an organisation with a tracked professional-network presence.
  - recent_funding: a dated funding round. Only applies to companies that raise outside capital; \
never choose it for schools, nonprofits, government bodies or bootstrapped small businesses.
  - topic_engagement: people at the buyer organisation publicly posting, in their own words and \
within the last months, about a topic that shows they are open to what the seller sells. Each \
post is dated and has a public link. This works for buyers that hiring and funding data do not \
cover, such as schools, clinics, agencies and local firms, as long as their staff post on a \
professional network. It REQUIRES topic_keywords: a plan that chooses it without keywords is \
discarded. The topic is NOT the buyer's everyday subject (a school's maths or teaching methods); \
it is their openness to the kind of change the seller brings. For an AI tutor sold to schools, a \
teacher who posts about AI is a stronger reason to reach out than the school merely existing.
  Pick only signal_types you expect this buyer type to actually have. If none of them \
realistically applies, leave signal_types empty and say so in open_questions or assumptions \
instead of guessing: an empty, honest list is better than one that will find nothing.
- exclusions: companies that must not be targeted (competitors, partners the seller depends \
on, existing customers named in the context). One company per item, written as \
"Name (domain.com)" when the domain is known; no explanations.
- tech_keywords: up to 6 product names the seller integrates with or replaces, exactly as \
written in the context (e.g. "Zendesk"). Job postings that name them are evidence of fit.
- topic_keywords: 3 to 6 short topics or phrases that someone at the buyer would post about if \
they were open to what the seller sells, worded as they would write them (for an AI maths tutor \
sold to schools: "AI", "edtech", "ChatGPT", "digital learning"; not "maths" or "teaching", which \
every teacher posts about). Never the seller's own name or product. Code searches public posts \
for these and checks each post really says one. MUST be filled whenever signal_types contains \
topic_engagement; leave empty only if it does not.
- dimensions: what the context says about any of these ICP dimensions: operational, problem, \
value, budget, readiness, buying_process, economics. One short sentence each. Leave a dimension \
out when the context does not support it; never guess.
- max_accounts: how many accounts to research (at most 25).
- assumptions: every choice you made that the context does not state.
- open_questions: at most 3 questions whose answers would change the targeting.

If the message contains <approved_lessons>, a person approved each one after seeing real \
outcomes. Prefer the signal types and topics they favor, and say in assumptions when you did. \
If one favors topic_engagement, choose it and give topic_keywords.

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
