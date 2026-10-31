"""Deterministic account selection after search: exclusions, identity and dedupe."""

from __future__ import annotations

from pydantic import BaseModel

from trigger_point.mission.models import GTMPlan
from trigger_point.providers.crustdata.models import Company


class RejectedCompany(BaseModel):
    provider_company_id: int
    name: str | None
    primary_domain: str | None
    reason: str  # seller_itself | excluded_domain | excluded_name | duplicate | no_domain


def select_accounts(
    companies: list[Company], plan: GTMPlan, seller_domain: str, seller_company_id: int | None
) -> tuple[list[Company], list[RejectedCompany]]:
    kept: list[Company] = []
    rejected: list[RejectedCompany] = []
    seen_ids: set[int] = set()
    seen_domains: set[str] = set()
    excluded_names = {n.casefold() for n in plan.excluded_names}
    for c in companies:
        domain = (c.primary_domain or "").removeprefix("www.")
        reason: str | None = None
        if c.provider_company_id == seller_company_id or domain == seller_domain:
            reason = "seller_itself"
        elif domain and domain in plan.excluded_domains:
            reason = "excluded_domain"
        elif c.name and c.name.casefold() in excluded_names:
            reason = "excluded_name"
        elif not domain:
            reason = "no_domain"
        elif c.provider_company_id in seen_ids or domain in seen_domains:
            reason = "duplicate"
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
