"""Topic engagement, step one: the search request, and the checks that make a post count.

The provider's match is fuzzy and its employer field is a name, not an id. So code re-checks both:
the keyword must really be in the text, and the employer must match the account by name, with
the weaker kind of match said out loud."""

from __future__ import annotations

import re
from datetime import date, timedelta

from trigger_point.mission.models import DEFAULT_FRESHNESS_DAYS, GTMPlan
from trigger_point.providers.crustdata.models import (
    Company,
    PostCondition,
    PostConditionGroup,
    PostSearchRequest,
)

MAX_TOPIC_KEYWORDS = 6
ACRONYM_LENGTH = 3  # up to this long, a keyword must match case, so "AI" is not "said" or "ai"
GENERIC_NAME_WORDS = frozenset(
    {"the", "of", "and", "pvt", "ltd", "private", "limited", "inc", "llc"}
)


def _name_tokens(name: str) -> frozenset[str]:
    return frozenset(re.findall(r"[a-z0-9]+", name.casefold())) - GENERIC_NAME_WORDS


def employer_matches(account_name: str | None, listed: str | None) -> bool:
    """True only when the author's employer is named exactly like the account (case, punctuation
    and words like "Pvt Ltd" aside). Posts carry the employer's name, not its id, and a chain's
    campuses are separate companies whose names carry the place ("... Jabalpur"), so a name that
    merely contains the account's is another campus or the group page, never a match."""
    if not account_name or not listed:
        return False
    a, b = _name_tokens(account_name), _name_tokens(listed)
    return bool(a) and a == b


def keyword_pattern(keyword: str) -> re.Pattern[str]:
    words = [re.escape(w) for w in keyword.split()]
    pattern = r"(?<![A-Za-z0-9])" + r"\s+".join(words) + r"(?![A-Za-z0-9])"
    return re.compile(pattern, 0 if len(keyword) <= ACRONYM_LENGTH else re.IGNORECASE)


def topic_hits(text: str, keywords: list[str]) -> list[str]:
    """The keywords the text really says, in the order they were asked for."""
    hits: list[str] = []
    for kw in keywords:
        k = " ".join(kw.split())
        if (
            k
            and keyword_pattern(k).search(text)
            and k.casefold() not in {h.casefold() for h in hits}
        ):
            hits.append(k)
    return hits


def compile_post_request(
    account: Company, plan: GTMPlan, today: date, limit: int
) -> PostSearchRequest | None:
    """One account, its own staff's original posts, on the plan's topics, inside the window.
    The topic is in the query because posts are billed per post returned."""
    keywords = [k for k in plan.topic_keywords if k.strip()][:MAX_TOPIC_KEYWORDS]
    if not keywords or not account.name:
        return None
    window = plan.freshness_days.get("topic_engagement", DEFAULT_FRESHNESS_DAYS["topic_engagement"])
    since = today - timedelta(days=window)
    return PostSearchRequest(
        filters=PostConditionGroup(
            op="and",
            conditions=[
                PostCondition(field="actor.actor_type", type="=", value="person"),
                PostCondition(field="post_type", type="=", value="original"),
                PostCondition(field="date_posted", type="=>", value=since.isoformat()),
                PostCondition(field="actor.company_name", type="[.]", value=account.name),
                PostConditionGroup(
                    op="or",
                    conditions=[PostCondition(field="text", type="[.]", value=k) for k in keywords],
                ),
            ],
        ),
        limit=limit,
    )
