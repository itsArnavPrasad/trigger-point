"""Social post search: typed, allowlisted, billed per post returned, and free of personal names."""

from decimal import Decimal
from typing import Any

import httpx
import pytest

from trigger_point.providers.crustdata.client import (
    CreditBudget,
    CrustdataClient,
    estimate_post_credits,
)
from trigger_point.providers.crustdata.errors import CrustdataError
from trigger_point.providers.crustdata.models import (
    PostCondition,
    PostConditionGroup,
    PostSearchRequest,
)

POSTS = {
    "posts": [
        {
            "share_url": "https://www.linkedin.example/posts/p1",
            "date_posted": "2026-10-20T09:26:04Z",
            "text": "Our maths teachers are trying AI tutors in Class 8 this term.",
            "post_type": "original",
            "actor": {
                "crustdata_entity_id": 777,
                "name": "Asha Example",
                "headline": "Teacher | learner",
                "title": "Senior Maths Teacher",
                "company_name": "Sunrise International School",
            },
        },
        {"share_url": None, "date_posted": None, "text": "No date here", "actor": {}},
    ],
    "next_cursor": None,
    "total_count": 2,
}


def client_for(body: Any, seen: list[httpx.Request], credits: str = "1.0") -> CrustdataClient:
    def handler(r: httpx.Request) -> httpx.Response:
        seen.append(r)
        return httpx.Response(200, json=body, headers={"x-credits-used": credits})

    return CrustdataClient(
        httpx.Client(transport=httpx.MockTransport(handler)), api_key="k", budget=CreditBudget(5)
    )


def req(limit: int = 2) -> PostSearchRequest:
    return PostSearchRequest(
        filters=PostConditionGroup(
            op="and",
            conditions=[
                PostCondition(field="actor.actor_type", type="=", value="person"),
                PostCondition(field="actor.company_name", type="(.)", value="Sunrise School"),
                PostCondition(field="date_posted", type="=>", value="2026-07-01"),
                PostConditionGroup(
                    op="or",
                    conditions=[PostCondition(field="text", type="[.]", value="AI")],
                ),
            ],
        ),
        limit=limit,
    )


def test_post_search_returns_dated_posts_and_keeps_unknown_unknown() -> None:
    seen: list[httpx.Request] = []
    result = client_for(POSTS, seen).search_posts(req())
    assert str(seen[0].url) == "https://api.crustdata.com/social_post/search"
    first, second = result.data.posts
    assert first.posted_on is not None and first.posted_on.isoformat() == "2026-10-20"
    assert first.author_id == 777 and first.author_title == "Senior Maths Teacher"
    assert first.author_company == "Sunrise International School"
    assert first.post_url == "https://www.linkedin.example/posts/p1"
    assert second.posted_on is None and second.post_url is None and second.author_id is None
    assert result.receipt.credits_used == Decimal("1.0")


def test_a_normalised_post_carries_no_personal_name_or_headline() -> None:
    page = client_for(POSTS, []).search_posts(req()).data
    dumped = " ".join(p.model_dump_json() for p in page.posts)
    assert "Asha" not in dumped and "learner" not in dumped


def test_the_request_asks_only_for_the_minimal_fields() -> None:
    seen: list[httpx.Request] = []
    client_for(POSTS, seen).search_posts(req())
    body = seen[0].read().decode()
    assert "actor.name" not in body and "actor.headline" not in body
    assert "reactors" not in body and "comments" not in body
    assert '"fields"' in body and "share_url" in body and "date_posted" in body


def test_post_filters_are_allowlisted() -> None:
    with pytest.raises(ValueError, match="not a supported"):
        PostCondition(field="reactors.name", type="=", value="x")


def test_post_fields_cannot_pull_reactors_or_comments() -> None:
    with pytest.raises(ValueError, match="selectable"):
        PostSearchRequest(
            filters=PostCondition(field="actor.actor_type", type="=", value="person"),
            fields=["reactors"],
        )


def test_the_estimate_is_half_a_credit_per_post_requested() -> None:
    assert estimate_post_credits(req(limit=4)) == Decimal("2.0")


def test_a_search_that_cannot_be_afforded_is_refused_before_any_call() -> None:
    seen: list[httpx.Request] = []
    tight = CrustdataClient(
        httpx.Client(transport=httpx.MockTransport(lambda r: seen.append(r))),  # type: ignore[arg-type,return-value]
        api_key="k",
        budget=CreditBudget(1),
    )
    with pytest.raises(CrustdataError) as err:
        tight.search_posts(req(limit=5))
    assert err.value.kind == "budget_exceeded" and seen == []


def test_an_empty_result_is_not_an_error_and_costs_nothing() -> None:
    body = {"posts": [], "next_cursor": None, "total_count": 0}
    result = client_for(body, [], credits="0").search_posts(req())
    assert result.data.posts == [] and result.receipt.credits_used == Decimal("0")


def test_a_malformed_response_is_a_typed_error() -> None:
    with pytest.raises(CrustdataError) as err:
        client_for({"posts": "nope"}, []).search_posts(req())
    assert err.value.kind == "malformed_response"
