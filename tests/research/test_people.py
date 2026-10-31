from tests.research.factories import person, plan
from trigger_point.research.people import compile_people_request, match_people


def test_exact_persona_title_is_full_confidence() -> None:
    [m] = match_people([person(title="Head of Support")], account_id=1001, plan=plan()).matches
    assert m.confidence == 1.0 and m.persona_title == "Head of Support"
    assert m.employer_verified is True


def test_function_plus_seniority_is_partial_confidence() -> None:
    [m] = match_people([person(title="Director, Customer Support")], 1001, plan()).matches
    assert m.confidence == 0.6


def test_individual_contributors_are_not_buyers() -> None:
    result = match_people([person(title="Customer Support Specialist")], 1001, plan())
    assert result.matches == []
    assert result.rejected[0].reason == "not_a_persona_match"


def test_employer_mismatch_is_rejected_even_with_perfect_title() -> None:
    result = match_people([person(cid=2002, title="Head of Support")], 1001, plan())
    assert result.matches == [] and result.rejected[0].reason == "current_employer_mismatch"


def test_best_match_is_deterministic() -> None:
    result = match_people(
        [
            person(pid=7, title="Director of Support"),
            person(pid=3, title="Head of Support"),
            person(pid=2, title="Head of Support"),
        ],
        1001,
        plan(),
    )
    assert [m.person.provider_person_id for m in result.matches] == [2, 3, 7]
    assert result.best is not None and result.best.person.provider_person_id == 2


def test_people_request_targets_accounts_and_function_keywords() -> None:
    req = compile_people_request([1001, 1002], plan(), limit=10)
    body = req.to_body()
    conds = body["filters"]["conditions"]
    assert conds[0] == {
        "field": "experience.employment_details.current.company_id",
        "type": "in",
        "value": [1001, 1002],
    }
    titles = [c["value"] for c in conds[1]["conditions"]]
    assert "support" in titles and body["limit"] == 10
