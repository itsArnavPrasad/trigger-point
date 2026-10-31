"""Deterministic job-search request for why-now postings at the researched accounts."""

from __future__ import annotations

from datetime import date, timedelta

from trigger_point.mission.models import DEFAULT_FRESHNESS_DAYS, GTMPlan
from trigger_point.providers.crustdata.models import (
    JobCondition,
    JobConditionGroup,
    JobSearchRequest,
    JobSort,
)
from trigger_point.research.signals import persona_keywords, posting_signal

MAX_TITLE_KEYWORDS = 8
JOB_FIELDS = [
    "crustdata_job_id",
    "job_details",
    "company.basic_info",
    "metadata",
    "content.description",
]


def compile_job_request(
    account_ids: list[int], plan: GTMPlan, reference_date: date, limit: int
) -> JobSearchRequest:
    signal = posting_signal(plan) or "support_team_growth"
    window = plan.freshness_days.get(signal, DEFAULT_FRESHNESS_DAYS[signal])
    since = reference_date - timedelta(days=window)
    conditions: list[JobCondition | JobConditionGroup] = [
        JobCondition(field="company.basic_info.company_id", type="in", value=list(account_ids)),
        JobCondition(field="metadata.date_added", type="=>", value=since.isoformat()),
    ]
    keywords = [k.strip() for k in persona_keywords(plan)][:MAX_TITLE_KEYWORDS]
    if keywords:
        conditions.append(
            JobConditionGroup(
                op="or",
                conditions=[
                    JobCondition(field="job_details.title", type="(.)", value=k) for k in keywords
                ],
            )
        )
    return JobSearchRequest(
        filters=JobConditionGroup(op="and", conditions=conditions),
        sorts=[JobSort(field="metadata.date_added", order="desc")],
        fields=JOB_FIELDS,
        limit=limit,
    )
