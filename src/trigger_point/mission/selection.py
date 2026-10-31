"""Deterministic account selection after search: exclusions, identity and dedupe."""

from __future__ import annotations

from pydantic import BaseModel

from trigger_point.mission.models import GTMPlan
from trigger_point.providers.crustdata.models import Company


class RejectedCompany(BaseModel):
    provider_company_id: int
    name: str | None
    primary_domain: str | None
    reason: str  # seller_itself | excluded_domain | excluded_name | duplicate | no_domain | wrong_country | not_the_buyer


# Unconditional: these names mark a board, coach or seller whatever else the name says.
BUYER_EXCLUSION_WORDS: tuple[str, ...] = (
    "board of",
    "coaching",
    "tuition",
    "tutorials",
    "test prep",
    "test-prep",
    "e-learning",
)

# Conditional: a name with one of these markers and no buyer word below is a seller —
# "Callido Learning" is not the buyer, but "The Learning Tree School" is, because it
# carries a buyer word.
SELLER_NAME_MARKERS: tuple[str, ...] = (
    "learning",
    "edtech",
    "labs",
    "technologies",
    "tech",
    "solutions",
    "systems",
    "software",
    "analytics",
    "app",
    "platform",
)

# Words that mark a name as a place where people are taught, not a company that sells to them.
BUYER_NAME_WORDS: tuple[str, ...] = (
    "school",
    "schools",
    "academy",
    "college",
    "university",
    "vidyalaya",
    "vidya",
    "vidyalay",
    "kindergarten",
    "matriculation",
    "inter college",
    "junior college",
    "public school",
    "high school",
    "degree college",
)

# Buyer segments an ICP may name. The exclusion above applies only when the ICP itself
# names one: a schools plan says "schools", so "edtech" in a result name is a competitor,
# but a companies plan for, say, edtech buyers must not reject "Callido Learning".
BUYER_SEGMENT_WORDS: tuple[str, ...] = (
    "school",
    "schools",
    "college",
    "university",
    "hospital",
    "clinic",
    "restaurant",
    "retailer",
    "manufacturer",
    "distributor",
    "law firm",
)

COUNTRY_CODES: dict[str, str] = {
    "india": "IND",
    "united states": "USA",
    "united kingdom": "GBR",
    "united arab emirates": "ARE",
    "singapore": "SGP",
}


def _country_codes(names: list[str]) -> set[str]:
    out: set[str] = set()
    for name in names:
        code = COUNTRY_CODES.get(name.strip().casefold())
        if code:
            out.add(code)
        elif len(name) == 3 and name.isalpha():
            out.add(name.upper())
    return out


def select_accounts(
    companies: list[Company], plan: GTMPlan, seller_domain: str, seller_company_id: int | None
) -> tuple[list[Company], list[RejectedCompany]]:
    kept: list[Company] = []
    rejected: list[RejectedCompany] = []
    seen_ids: set[int] = set()
    seen_domains: set[str] = set()
    excluded_names = {n.casefold() for n in plan.excluded_names}
    want_countries = _country_codes(plan.countries)
    # The buyer rule is on only when the ICP names a buyer segment. A schools plan says
    # "schools", so "Callido Learning" in the results is a competitor, not the buyer.
    # A plan that names no segment keeps the rule off and cannot reject a real buyer by name.
    buyer_rule_on = any(w in plan.icp_query.casefold() for w in BUYER_SEGMENT_WORDS)
    for c in companies:
        domain = (c.primary_domain or "").removeprefix("www.")
        name_fold = (c.name or "").casefold()
        reason: str | None = None
        if c.provider_company_id == seller_company_id or domain == seller_domain:
            reason = "seller_itself"
        elif domain and domain in plan.excluded_domains:
            reason = "excluded_domain"
        elif c.name and name_fold in excluded_names:
            reason = "excluded_name"
        elif not domain:
            reason = "no_domain"
        elif c.provider_company_id in seen_ids or domain in seen_domains:
            reason = "duplicate"
        elif want_countries and (c.hq_country or "").upper() not in want_countries:
            # The place filter is fuzzy and leaked an ARE school for a Mumbai plan (proven
            # live), so the returned record is re-checked against the plan's countries.
            reason = "wrong_country"
        elif (
            buyer_rule_on
            and name_fold
            and any(w in name_fold for w in BUYER_EXCLUSION_WORDS)
            or (
                buyer_rule_on
                and name_fold
                and any(w in name_fold for w in SELLER_NAME_MARKERS)
                and not any(w in name_fold for w in BUYER_NAME_WORDS)
            )
        ):
            reason = "not_the_buyer"
        if reason:
            rejected.append(
                RejectedCompany(
                    provider_company_id=c.provider_company_id,
                    name=c.name,
                    primary_domain=c.primary_domain,
                    reason=reason,
                )
            )
            continue
        seen_ids.add(c.provider_company_id)
        seen_domains.add(domain)
        kept.append(c)
    return kept, rejected
