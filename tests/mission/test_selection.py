"""Post-filter account selection: the API's fuzzy filters leak, so code is the gate."""

from __future__ import annotations

from datetime import UTC, datetime

from trigger_point.mission.models import GTMPlan
from trigger_point.mission.selection import select_accounts
from trigger_point.providers.crustdata.models import Company


def company(
    pid: int, name: str, domain: str, country: str | None = "IND"
) -> Company:
    return Company(
        provider_company_id=pid,
        name=name,
        primary_domain=domain,
        hq_country=country,
        retrieved_at=datetime.now(UTC),
        source_endpoint="/company/search",
    )


def plan(**over: object) -> GTMPlan:
    base: dict[str, object] = {
        "icp_query": "schools in Mumbai",
        "countries": ["IND"],
        "max_accounts": 10,
        "credit_budget": 5,
    }
    base.update(over)
    return GTMPlan(**base)  # type: ignore[arg-type]


def test_a_record_outside_the_plan_countries_is_rejected() -> None:
    # Live finding: `locations.headquarters (.) Mumbai` returned an ARE (Dubai) school.
    kept, rejected = select_accounts(
        [company(1, "Dubai Modern Education School", "dubaischool.ae", "ARE")],
        plan(),
        "learntulip.com",
        None,
    )
    assert not kept
    assert rejected[0].reason == "wrong_country"


def test_a_record_with_no_country_when_the_plan_names_one_is_rejected() -> None:
    kept, rejected = select_accounts(
        [company(2, "Unknown School", "unknown.school", None)],
        plan(),
        "learntulip.com",
        None,
    )
    assert not kept and rejected[0].reason == "wrong_country"


def test_a_matching_country_is_kept() -> None:
    kept, rejected = select_accounts(
        [company(3, "Dhirubhai Ambani International School", "da-is.org", "IND")],
        plan(),
        "learntulip.com",
        None,
    )
    assert len(kept) == 1 and not rejected


def test_seller_type_names_are_rejected_as_not_the_buyer() -> None:
    # Live finding: the search returned the CBSE board and coaching centres for a schools ICP.
    names = [
        ("Central Board of Secondary Education", "cbse.gov.in"),
        ("FIITJEE Mumbai Coaching Centre", "fiitjee.com"),
        ("Callido Learning", "callidolearning.com"),
    ]
    kept, rejected = select_accounts(
        [company(i, n, d) for i, (n, d) in enumerate(names)], plan(), "learntulip.com", None
    )
    assert not kept
    assert {r.reason for r in rejected} == {"not_the_buyer"}


def test_a_school_with_a_name_like_a_seller_is_not_rejected() -> None:
    # "Learning academy" appears inside real school names too; the rule is bounded,
    # so a plain school name must survive.
    kept, rejected = select_accounts(
        [company(9, "Green Lawns High School", "greenlawns.org")],
        plan(),
        "learntulip.com",
        None,
    )
    assert len(kept) == 1 and not rejected


def test_no_country_filter_means_no_country_rejection() -> None:
    kept, rejected = select_accounts(
        [company(4, "Any School", "any.school", None)], plan(countries=[]), "learntulip.com", None
    )
    assert len(kept) == 1 and not rejected


def test_the_buyer_rule_never_rejects_when_no_buyer_words_are_named() -> None:
    # A plan for companies has no seller words; nothing should be dropped by name.
    kept, _ = select_accounts(
        [company(5, "Acme Robotics", "acme.io")],
        plan(icp_query="companies hiring support engineers"),
        "learntulip.com",
        None,
    )
    assert len(kept) == 1
