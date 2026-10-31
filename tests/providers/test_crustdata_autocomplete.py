"""Crustdata matches industry and place text exactly, with case. Autocomplete is free and returns the
values it really has, so names are resolved through it before any paid search."""

import json
from typing import Any

import httpx
import pytest

from tests.providers.test_crustdata_client import make, resp
from trigger_point.providers.crustdata.errors import CrustdataError
from trigger_point.providers.crustdata.names import resolve_names


def suggest(*values: str) -> dict[str, Any]:
    return {"suggestions": [{"value": v} for v in values]}


def test_autocomplete_returns_the_providers_values_and_costs_nothing() -> None:
    seen: list[httpx.Request] = []

    def handler(r: httpx.Request) -> httpx.Response:
        seen.append(r)
        return resp(200, suggest("Primary/Secondary Education"), **{"x-credits-used": "0"})

    client, _ = make(handler)
    out = client.autocomplete_company("basic_info.industries", "primary/secondary education")
    assert out.data == ["Primary/Secondary Education"] and out.receipt.credits_used == 0
    assert str(seen[0].url) == "https://api.crustdata.com/company/search/autocomplete"
    assert json.loads(seen[0].content) == {
        "field": "basic_info.industries",
        "query": "primary/secondary education",
        "limit": 8,
    }


def test_only_known_fields_can_be_completed() -> None:
    client, _ = make(lambda r: resp(200, suggest()))
    with pytest.raises(ValueError, match="not a supported"):
        client.autocomplete_company("basic_info.ceo_email", "x")


def test_a_malformed_answer_is_a_typed_error() -> None:
    client, _ = make(lambda r: resp(200, {"suggestions": "nope"}))
    with pytest.raises(CrustdataError) as err:
        client.autocomplete_company("basic_info.industries", "x")
    assert err.value.kind == "malformed_response"


def test_a_name_in_the_wrong_case_becomes_the_providers_spelling() -> None:
    client, _ = make(
        lambda r: resp(200, suggest("Primary/Secondary Education", "Language Schools"))
    )
    names, notes = resolve_names(client, "basic_info.industries", ["primary/secondary education"])
    assert names == ["Primary/Secondary Education"]
    assert "primary/secondary education" in notes[0] and "Primary/Secondary Education" in notes[0]


def test_an_exact_name_is_kept_without_a_note() -> None:
    client, _ = make(lambda r: resp(200, suggest("Primary/Secondary Education")))
    names, notes = resolve_names(client, "basic_info.industries", ["Primary/Secondary Education"])
    assert names == ["Primary/Secondary Education"] and notes == []


def test_a_name_with_no_exact_match_is_kept_as_given_never_guessed() -> None:
    client, _ = make(lambda r: resp(200, suggest("Language Schools", "Fine Arts Schools")))
    names, notes = resolve_names(client, "basic_info.industries", ["school"])
    assert names == ["school"] and "not recognised" in notes[0]


def test_a_failing_lookup_keeps_the_names_and_says_so() -> None:
    client, _ = make(lambda r: resp(500, {"error": "down"}), max_retries=0)
    names, notes = resolve_names(client, "locations.headquarters", ["Powai"])
    assert names == ["Powai"] and "could not be checked" in notes[0]


def test_duplicates_collapse_after_resolving() -> None:
    client, _ = make(lambda r: resp(200, suggest("Primary/Secondary Education")))
    names, _ = resolve_names(
        client,
        "basic_info.industries",
        ["primary/secondary education", "PRIMARY/SECONDARY EDUCATION"],
    )
    assert names == ["Primary/Secondary Education"]


def test_a_plan_is_given_the_providers_spelling_for_industries_and_places() -> None:
    from tests.research.factories import plan
    from trigger_point.providers.crustdata.names import canonical_plan

    answers = {
        "basic_info.industries": suggest("Primary/Secondary Education"),
        "locations.headquarters": suggest("Powai, Mumbai, Maharashtra, India"),
    }

    def handler(r: httpx.Request) -> httpx.Response:
        return resp(200, answers[json.loads(r.content)["field"]])

    client, _ = make(handler)
    p = plan(
        industries=["primary/secondary education"],
        places=["powai, mumbai, maharashtra, india"],
    )
    fixed, notes = canonical_plan(client, p)
    assert fixed.industries == ["Primary/Secondary Education"]
    assert fixed.places == ["Powai, Mumbai, Maharashtra, India"]
    assert len(notes) == 2 and fixed.countries == p.countries


def test_a_plan_with_nothing_to_resolve_makes_no_calls() -> None:
    from tests.research.factories import plan
    from trigger_point.providers.crustdata.names import canonical_plan

    calls: list[int] = []
    client, _ = make(lambda r: calls.append(1) or resp(200, suggest()))  # type: ignore[func-returns-value]
    fixed, notes = canonical_plan(client, plan(industries=[], places=[]))
    assert calls == [] and notes == [] and fixed.industries == []


def test_the_same_words_spelled_with_a_slash_or_and_are_both_searched() -> None:
    # Seen live: "Primary/Secondary Education" holds no companies; "Primary and Secondary
    # Education" holds the schools. Both are in the taxonomy, so both go in the filter.
    client, _ = make(
        lambda r: resp(
            200,
            suggest("Primary and Secondary Education", "Primary/Secondary Education", "Education"),
        )
    )
    names, notes = resolve_names(client, "basic_info.industries", ["primary/secondary education"])
    assert names == ["Primary/Secondary Education", "Primary and Secondary Education"]
    assert "Primary and Secondary Education" in notes[0]


def test_the_and_form_of_a_slash_name_is_looked_up_too() -> None:
    def handler(r: httpx.Request) -> httpx.Response:
        q = json.loads(r.content)["query"]
        if "/" in q:
            return resp(200, suggest("Primary/Secondary Education"))
        return resp(200, suggest("Primary and Secondary Education"))

    client, _ = make(handler)
    names, _ = resolve_names(client, "basic_info.industries", ["primary/secondary education"])
    assert names == ["Primary/Secondary Education", "Primary and Secondary Education"]
