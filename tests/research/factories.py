from datetime import UTC, date, datetime
from typing import Any

from trigger_point.mission.models import GTMPlan, PersonaTarget
from trigger_point.providers.crustdata.models import Company, JobPosting, PersonRecord

TODAY = date(2026, 10, 31)
NOW = datetime(2026, 10, 31, tzinfo=UTC)


def plan(**over: Any) -> GTMPlan:
    base: dict[str, Any] = dict(
        icp_query="B2B SaaS companies scaling support",
        countries=["USA", "CAN"],
        employee_ranges=["51-200", "201-500", "501-1000"],
        personas=[
            PersonaTarget(
                title="Head of Support",
                function="customer_success_and_support",
                why="Owns ticket volume",
            )
        ],
        signal_types=["support_team_growth", "active_hiring", "headcount_growth"],
        excluded_domains=["supportpilot.example"],
        max_accounts=10,
        credit_budget=5.0,
        freshness_days={"support_team_growth": 30, "active_hiring": 30, "headcount_growth": 180},
        tech_keywords=["Zendesk", "Intercom"],
    )
    base.update(over)
    return GTMPlan(**base)


def company(cid: int = 1001, **over: Any) -> Company:
    base: dict[str, Any] = dict(
        provider_company_id=cid,
        name="Ledgerloop",
        primary_domain="ledgerloop.example",
        employee_count_range="201-500",
        headcount_total=340,
        headcount_growth_6m_pct=14.2,
        hiring_openings=12,
        hq_country="USA",
        provider_updated_at="2026-10-21T00:00:00Z",
        retrieved_at=NOW,
        source_endpoint="/company/search",
    )
    base.update(over)
    return Company(**base)


def posting(job_id: int = 9001, cid: int = 1001, **over: Any) -> JobPosting:
    base: dict[str, Any] = dict(
        provider_job_id=job_id,
        company_id=cid,
        company_name="Ledgerloop",
        title="Customer Support Specialist",
        category="Customer Service",
        url=f"https://jobs.example/{job_id}",
        posted_on=date(2026, 10, 15),
        last_seen_on=date(2026, 10, 28),
        description="Resolve tickets in Zendesk daily.",
        retrieved_at=NOW,
    )
    base.update(over)
    return JobPosting(**base)


def person(
    pid: int = 501, cid: int = 1001, title: str = "Head of Support", **over: Any
) -> PersonRecord:
    base: dict[str, Any] = dict(
        provider_person_id=pid,
        name="Ana Example",
        current_title=title,
        current_company_ids=[cid],
        current_titles=[title],
        current_role_start="2025-02-01",
        profile_url=f"https://profiles.example/{pid}",
        provider_updated_at="2026-10-04T00:00:00Z",
        retrieved_at=NOW,
    )
    base.update(over)
    return PersonRecord(**base)
