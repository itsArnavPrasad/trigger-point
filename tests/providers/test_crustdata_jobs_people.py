import json
from decimal import Decimal
from typing import Any

import httpx
import pytest

from trigger_point.providers.crustdata.client import (
    CreditBudget,
    CrustdataClient,
    estimate_job_credits,
    estimate_person_credits,
)
from trigger_point.providers.crustdata.models import (
    JobCondition,
    JobConditionGroup,
    JobSearchRequest,
    PersonCondition,
    PersonConditionGroup,
    PersonSearchRequest,
)

JOBS = {
    "job_listings": [
        {
            "crustdata_job_id": 9001,
            "job_details": {
                "title": "Customer Support Specialist",
                "category": "Customer Service",
                "url": "https://www.linkedin.example/jobs/view/9001",
            },
            "company": {
                "basic_info": {
                    "crustdata_company_id": 1001,
                    "name": "Ledgerloop",
                    "primary_domain": "ledgerloop.example",
                }
            },
            "metadata": {
                "date_added": "2026-10-15T00:00:00",
                "date_updated": "2026-10-28T00:00:00",
            },
            "content": {"description": "You will resolve tickets in Zendesk and Intercom."},
        },
        {
            "crustdata_job_id": 9002,
            "job_details": {"title": "Support Lead", "url": None},
            "company": {"basic_info": {"crustdata_company_id": 1002}},
            "metadata": {"date_added": None, "date_updated": None},
        },
    ],
    "next_cursor": None,
    "total_count": 2,
}

PEOPLE = {
    "profiles": [
        {
            "crustdata_person_id": 501,
            "basic_profile": {"name": "Ana Example", "current_title": "Head of Support"},
            "experience": {
                "employment_details": {
                    "current": [
                        {
                            "title": "Head of Support",
                            "crustdata_company_id": 1001,
                            "start_date": "2025-02-01",
                        }
                    ]
                }
            },
            "social_handles": {
                "professional_network_identifier": {
                    "profile_url": "https://www.linkedin.example/in/ana-example"
                }
            },
            "metadata": {"updated_at": "2026-10-04T00:00:00Z"},
        },
    ],
    "next_cursor": None,
    "total_count": 1,
}


def client_for(body: Any, seen: list[httpx.Request]) -> CrustdataClient:
    def handler(r: httpx.Request) -> httpx.Response:
        seen.append(r)
        return httpx.Response(200, json=body, headers={"x-credits-used": "0.06"})

    return CrustdataClient(
        httpx.Client(transport=httpx.MockTransport(handler)), api_key="k", budget=CreditBudget(5)
    )


def job_req() -> JobSearchRequest:
    return JobSearchRequest(
        filters=JobConditionGroup(
            op="and",
            conditions=[
                JobCondition(field="company.basic_info.company_id", type="in", value=[1001, 1002]),
                JobCondition(field="metadata.date_added", type="=>", value="2026-10-01"),
                JobConditionGroup(
                    op="or",
                    conditions=[
                        JobCondition(field="job_details.title", type="(.)", value="support"),
                    ],
                ),
            ],
        ),
        fields=[
            "crustdata_job_id",
            "job_details",
            "company.basic_info",
            "metadata",
            "content.description",
        ],
        limit=25,
    )


def test_job_search_normalises_event_and_last_seen_dates() -> None:
    seen: list[httpx.Request] = []
    result = client_for(JOBS, seen).search_jobs(job_req())
    assert str(seen[0].url) == "https://api.crustdata.com/job/search"
    first, second = result.data.postings
    assert first.company_id == 1001 and first.posted_on.isoformat() == "2026-10-15"
    assert first.last_seen_on is not None and first.last_seen_on.isoformat() == "2026-10-28"
    assert first.url == "https://www.linkedin.example/jobs/view/9001"
    assert "Zendesk" in (first.description or "")
    assert second.posted_on is None and second.url is None  # unknown stays unknown
    assert result.receipt.credits_used == Decimal("0.06")


def test_job_filters_are_allowlisted() -> None:
    with pytest.raises(ValueError, match="not a supported"):
        JobCondition(field="headcount.total", type=">", value=5)


def test_person_search_normalises_current_employers_without_contact_data() -> None:
    seen: list[httpx.Request] = []
    req = PersonSearchRequest(
        filters=PersonConditionGroup(
            op="and",
            conditions=[
                PersonCondition(
                    field="experience.employment_details.current.company_id",
                    type="in",
                    value=[1001],
                ),
                PersonCondition(
                    field="experience.employment_details.current.title", type="(.)", value="support"
                ),
            ],
        ),
        limit=10,
    )
    [person] = client_for(PEOPLE, seen).search_people(req).data.people
    body = json.loads(seen[0].content)
    assert str(seen[0].url) == "https://api.crustdata.com/person/search"
    assert "contact" not in json.dumps(body["fields"])
    assert person.current_company_ids == [1001]
    assert person.profile_url == "https://www.linkedin.example/in/ana-example"
    assert not hasattr(person, "email")


def test_person_filters_are_allowlisted() -> None:
    with pytest.raises(ValueError, match="not a supported"):
        PersonCondition(field="contact.business_emails", type="=", value="x")


def test_credit_estimates() -> None:
    assert estimate_job_credits(job_req()) == Decimal("0.03") * 25
    req = PersonSearchRequest(
        filters=PersonCondition(
            field="experience.employment_details.current.company_id", type="in", value=[1]
        ),
        limit=10,
    )
    assert estimate_person_credits(req) == Decimal("0.23") * 10
