from decimal import Decimal

import pytest

from trigger_point.mission.compiler import (
    compile_plan,
    compile_search_request,
    favour_signals,
    relaxation_steps,
)
from trigger_point.mission.models import MissionDraft, PersonaDraft
from trigger_point.providers.crustdata.client import estimate_search_credits
from trigger_point.providers.crustdata.models import Condition, ConditionGroup


def draft(**over: object) -> MissionDraft:
    base: dict[str, object] = dict(
        icp_query="B2B SaaS companies with growing customer support teams",
        countries=["United States", "Canada"],
        employee_min=50,
        employee_max=1000,
        personas=[
            PersonaDraft(
                title="Head of Support",
                function="customer_success_and_support",
                why="Owns ticket volume and support headcount",
            )
        ],
        signal_types=["support_team_growth", "active_hiring"],
        exclusions=["Zendesk"],
        max_accounts=10,
        assumptions=["Targets companies already on a helpdesk"],
        open_questions=[],
        topic_keywords=[],
        industries=[],
        places=[],
    )
    base.update(over)
    return MissionDraft(**base)  # type: ignore[arg-type]


def test_compile_plan_maps_countries_and_size_buckets() -> None:
    plan = compile_plan(draft(), seller_domain="supportpilot.example", credit_budget=5.0)
    assert plan.countries == ["USA", "CAN"]
    assert plan.employee_ranges == ["51-200", "201-500", "501-1000"]
    assert "supportpilot.example" in plan.excluded_domains


def test_unknown_country_and_signal_are_dropped_with_assumptions() -> None:
    plan = compile_plan(
        draft(countries=["Atlantis", "UK"], signal_types=["vibes", "recent_funding"]),
        seller_domain="s.example",
        credit_budget=5.0,
    )
    assert plan.countries == ["GBR"]
    assert plan.signal_types == ["recent_funding"]
    assert any("Atlantis" in a for a in plan.assumptions)
    assert any("vibes" in a for a in plan.assumptions)


def test_region_expands_deterministically() -> None:
    plan = compile_plan(
        draft(countries=["North America"]), seller_domain="s.example", credit_budget=5.0
    )
    assert plan.countries == ["USA", "CAN"]


def test_max_accounts_is_capped() -> None:
    plan = compile_plan(draft(max_accounts=500), seller_domain="s.example", credit_budget=5.0)
    assert plan.max_accounts == 25
    assert any("capped" in a for a in plan.assumptions)


def test_search_request_uses_only_allowlisted_free_filters_and_fits_budget() -> None:
    plan = compile_plan(draft(), seller_domain="s.example", credit_budget=5.0)
    req = compile_search_request(plan)
    assert req.search is not None and "customer support" in req.search.query
    assert isinstance(req.filters, ConditionGroup)
    fields = {c.field for c in req.filters.conditions if isinstance(c, Condition)}
    assert fields == {"locations.country", "basic_info.employee_count_range"}
    assert estimate_search_credits(req) <= Decimal("5.0")
    assert req.limit >= 1 and req.limit <= 100
    assert set(req.fields or []) >= {"basic_info", "headcount", "hiring"}


def test_requesting_funding_is_opt_in_by_signal_type() -> None:
    plain = compile_search_request(
        compile_plan(draft(), seller_domain="s.example", credit_budget=5.0)
    )
    assert "funding" not in (plain.fields or [])
    wanting = compile_search_request(
        compile_plan(
            draft(signal_types=["recent_funding"]), seller_domain="s.example", credit_budget=5.0
        )
    )
    assert "funding" in (wanting.fields or [])


def test_topic_keywords_are_cleaned_deduplicated_and_capped() -> None:
    messy = ["AI", " ai ", "edtech  ", "", "x" * 100, "a", "b", "c", "d", "e", "f"]
    plan = compile_plan(
        draft(signal_types=["topic_engagement"], topic_keywords=messy),
        seller_domain="s.example",
        credit_budget=5.0,
    )
    assert plan.topic_keywords[:2] == ["AI", "edtech"]
    assert len(plan.topic_keywords) == 6
    assert all(0 < len(k) <= 40 for k in plan.topic_keywords)


def test_topic_engagement_is_a_known_signal_with_its_own_window() -> None:
    plan = compile_plan(
        draft(signal_types=["topic_engagement"], topic_keywords=["AI"]),
        seller_domain="s.example",
        credit_budget=5.0,
    )
    assert plan.signal_types == ["topic_engagement"]
    assert plan.freshness_days["topic_engagement"] == 120


def test_topic_engagement_with_no_topic_is_dropped_and_says_so() -> None:
    plan = compile_plan(
        draft(signal_types=["topic_engagement", "active_hiring"], topic_keywords=[]),
        seller_domain="s.example",
        credit_budget=5.0,
    )
    assert plan.signal_types == ["active_hiring"]
    assert any("topic_engagement" in a and "keywords" in a for a in plan.assumptions)


def test_a_topic_that_only_describes_the_buyer_is_dropped_with_a_note() -> None:
    plan = base_plan(
        icp_query="CBSE schools in Powai, Mumbai teaching Classes 6 to 10",
        signal_types=["topic_engagement"],
        topic_keywords=["AI in education", "edtech", "CBSE", "Classes 6 to 10"],
    )
    assert plan.topic_keywords == ["AI in education", "edtech"]
    dropped = " ".join(a for a in plan.assumptions if "describes the buyer" in a)
    assert "'CBSE'" in dropped and "'Classes 6 to 10'" in dropped


def test_a_short_keyword_is_not_confused_with_a_longer_word() -> None:
    plan = base_plan(
        icp_query="schools in Powai, Mumbai",
        signal_types=["topic_engagement"],
        topic_keywords=["AI"],
    )
    assert plan.topic_keywords == ["AI"]  # "ai" is inside Powai and Mumbai, but not a word there


def test_if_every_topic_only_describes_the_buyer_the_signal_is_dropped() -> None:
    plan = base_plan(
        icp_query="CBSE schools in Powai",
        signal_types=["topic_engagement", "active_hiring"],
        topic_keywords=["CBSE", "schools"],
    )
    assert plan.topic_keywords == [] and plan.signal_types == ["active_hiring"]
    assert any("topic_engagement" in a and "keywords" in a for a in plan.assumptions)


def test_industries_and_places_become_filters() -> None:
    plan = base_plan(industries=["Primary and Secondary Education"], places=["Powai", "Mumbai"])
    req = compile_search_request(plan)
    assert isinstance(req.filters, ConditionGroup)
    flat = {c.field: c for c in req.filters.conditions if isinstance(c, Condition)}
    assert flat["basic_info.industries"].value == ["Primary and Secondary Education"]
    where = next(
        c for c in req.filters.conditions if isinstance(c, ConditionGroup) and c.op == "or"
    )
    assert [c.value for c in where.conditions if isinstance(c, Condition)] == ["Powai", "Mumbai"]  # type: ignore[union-attr]


def test_a_single_place_is_one_condition_not_a_group() -> None:
    req = compile_search_request(base_plan(places=["Mumbai"]))
    assert isinstance(req.filters, ConditionGroup)
    place = next(
        c for c in req.filters.conditions if getattr(c, "field", "") == "locations.headquarters"
    )
    assert place.type == "(.)" and place.value == "Mumbai"  # type: ignore[union-attr]


def test_industries_and_places_are_cleaned_and_capped() -> None:
    plan = base_plan(
        industries=[
            " Software  Development ",
            "software development",
            "",
            "x" * 200,
            "A",
            "B",
            "C",
            "D",
            "E",
        ],
        places=["Powai ", "powai", "", "Mumbai", "Thane", "Pune", "Delhi", "Goa"],
    )
    assert plan.industries[0] == "Software Development" and len(plan.industries) == 5
    assert plan.places[:2] == ["Powai", "Mumbai"] and len(plan.places) == 4
    assert all(0 < len(x) <= 60 for x in [*plan.industries, *plan.places])


def test_relaxation_drops_the_loosest_text_filters_before_the_country() -> None:
    plan = base_plan(industries=["Primary and Secondary Education"], places=["Mumbai"])
    steps = relaxation_steps(plan)
    assert [s.description for s in steps] == [
        "drop company-size filter",
        "drop place filter",
        "drop industry filter",
        "drop country filter",
    ]
    assert steps[1].plan.places == [] and steps[1].plan.industries == plan.industries
    assert steps[2].plan.industries == [] and steps[2].plan.countries == plan.countries


def test_the_model_must_answer_for_industries_and_places_every_time() -> None:
    required = MissionDraft.model_json_schema()["required"]
    assert "industries" in required and "places" in required


def test_the_model_must_answer_for_topic_keywords_every_time() -> None:
    # Fields with defaults are optional in the strict JSON schema, and a live model skipped this
    # one while choosing the signal that needs it. Required means it must say, even if empty.
    assert "topic_keywords" in MissionDraft.model_json_schema()["required"]


def base_plan(**over: object):  # type: ignore[no-untyped-def]
    return compile_plan(draft(**over), seller_domain="s.example", credit_budget=5.0)


def test_an_approved_lesson_adds_the_favoured_signal_and_says_why() -> None:
    plan = favour_signals(base_plan(signal_types=["active_hiring"]), ["recent_funding"])
    assert plan.signal_types == ["active_hiring", "recent_funding"]
    assert plan.freshness_days["recent_funding"] == 90
    assert any("recent_funding" in a and "approved lesson" in a for a in plan.assumptions)


def test_a_signal_already_chosen_is_not_added_twice() -> None:
    plan = favour_signals(base_plan(signal_types=["active_hiring"]), ["active_hiring"])
    assert plan.signal_types == ["active_hiring"]
    assert not any("approved lesson" in a for a in plan.assumptions)


def test_a_favoured_topic_signal_without_keywords_is_skipped_with_a_note() -> None:
    plan = favour_signals(base_plan(signal_types=["active_hiring"]), ["topic_engagement"])
    assert plan.signal_types == ["active_hiring"]
    assert any("topic_engagement" in a and "keywords" in a for a in plan.assumptions)


def test_a_favoured_topic_signal_with_keywords_is_added() -> None:
    plan = favour_signals(
        base_plan(signal_types=["active_hiring"], topic_keywords=["AI"]), ["topic_engagement"]
    )
    assert "topic_engagement" in plan.signal_types


def test_an_unknown_favoured_signal_is_ignored() -> None:
    plan = favour_signals(base_plan(signal_types=["active_hiring"]), ["mind_reading"])
    assert plan.signal_types == ["active_hiring"]


def test_compilation_is_deterministic() -> None:
    a = compile_search_request(compile_plan(draft(), seller_domain="s.example", credit_budget=5.0))
    b = compile_search_request(compile_plan(draft(), seller_domain="s.example", credit_budget=5.0))
    assert a.to_body() == b.to_body()


def test_budget_too_small_for_one_result_is_an_error() -> None:
    plan = compile_plan(draft(), seller_domain="s.example", credit_budget=0.1)
    with pytest.raises(ValueError, match="budget"):
        compile_search_request(plan)


def test_relaxation_drops_one_constraint_at_a_time() -> None:
    plan = compile_plan(draft(), seller_domain="s.example", credit_budget=5.0)
    steps = relaxation_steps(plan)
    assert [s.description for s in steps] == [
        "drop company-size filter",
        "drop country filter",
    ]
    assert steps[0].plan.employee_ranges == [] and steps[0].plan.countries == ["USA", "CAN"]
    assert steps[1].plan.employee_ranges == [] and steps[1].plan.countries == []


def test_no_filters_at_all_still_compiles_to_ranked_search() -> None:
    plan = compile_plan(
        draft(countries=[], employee_min=None, employee_max=None),
        seller_domain="s.example",
        credit_budget=5.0,
    )
    req = compile_search_request(plan)
    assert req.filters is None and req.search is not None


def test_prose_exclusions_are_parsed_into_domains_and_short_names() -> None:
    plan = compile_plan(
        draft(
            exclusions=[
                "Cloudflare (cloudflare.com) — competitor (Cloudflare Web Analytics)",
                "Existing customers named as proof: Stripe (stripe.com), Mozilla (mozilla.org)",
                "Zendesk",
                "intercom.com",
                "e.g. any agency",
            ]
        ),
        seller_domain="plausible.io",
        credit_budget=5.0,
    )
    assert {"cloudflare.com", "stripe.com", "mozilla.org", "intercom.com", "plausible.io"} <= set(
        plan.excluded_domains
    )
    assert "Cloudflare" in plan.excluded_names and "Zendesk" in plan.excluded_names
    assert not any("customers" in n.lower() for n in plan.excluded_names)
    assert "e.g" not in plan.excluded_domains


def test_no_freshness_window_exceeds_the_120_day_policy() -> None:
    # docs/EVIDENCE_AND_VERIFICATION.md: signals older than 120 days are normally not hooks.
    from trigger_point.mission.models import DEFAULT_FRESHNESS_DAYS

    assert max(DEFAULT_FRESHNESS_DAYS.values()) <= 120


def test_a_place_is_widened_one_part_at_a_time_before_it_is_dropped() -> None:
    from tests.research.factories import plan

    p = plan(places=["Powai, Mumbai, Maharashtra, India"], industries=[], employee_ranges=[])
    steps = [s.description for s in relaxation_steps(p)]
    assert steps[:3] == [
        "widen place to Mumbai, Maharashtra, India",
        "widen place to Maharashtra, India",
        "drop place filter",
    ]


def test_widening_keeps_the_other_filters() -> None:
    from tests.research.factories import plan

    p = plan(
        places=["Powai, Mumbai, India"],
        industries=["Primary/Secondary Education"],
        employee_ranges=[],
    )
    first = relaxation_steps(p)[0]
    assert first.plan.places == ["Mumbai, India"]
    assert first.plan.industries == ["Primary/Secondary Education"]
