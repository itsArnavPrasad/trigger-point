from tests.providers.crustdata_payloads import CASHFREE, NO_MATCH, SERVE_BY_NAME, match
from trigger_point.providers.crustdata.identity import (
    Ambiguous,
    NotFound,
    Resolved,
    resolve_identity,
)
from trigger_point.providers.crustdata.models import IdentifyResult


def parse(raw: list[dict]) -> IdentifyResult:  # type: ignore[type-arg]
    return IdentifyResult.model_validate(raw[0])


def test_showcase_pages_are_excluded_for_exact_domain() -> None:
    res = resolve_identity(parse(CASHFREE), queried_domain="cashfree.com")
    assert isinstance(res, Resolved)
    assert res.company_id == 622934
    assert "showcase" in res.reason


def test_several_distinct_companies_are_ambiguous_not_first() -> None:
    res = resolve_identity(parse(SERVE_BY_NAME), queried_domain=None)
    assert isinstance(res, Ambiguous)
    assert {c.crustdata_company_id for c in res.candidates} == {628895, 5825197, 25592234}


def test_no_match_is_not_found() -> None:
    assert isinstance(resolve_identity(parse(NO_MATCH), queried_domain="x.com"), NotFound)


def test_low_confidence_single_match_is_ambiguous() -> None:
    raw = [
        {
            "matched_on": "acme",
            "match_type": "name",
            "matches": [match(1, "Acme", "acme.com", "https://www.linkedin.com/company/acme", 0.6)],
        }
    ]
    assert isinstance(resolve_identity(parse(raw), queried_domain=None), Ambiguous)


def test_single_confident_match_resolves() -> None:
    raw = [
        {
            "matched_on": "acme.com",
            "match_type": "domain",
            "matches": [match(1, "Acme", "acme.com", "https://www.linkedin.com/company/acme")],
        }
    ]
    res = resolve_identity(parse(raw), queried_domain="acme.com")
    assert isinstance(res, Resolved) and res.company_id == 1
