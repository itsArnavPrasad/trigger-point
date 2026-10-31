"""Evidence audit and quality gate: deterministic verdicts, never a model's opinion."""

from datetime import UTC, date, datetime

from trigger_point.models.evidence import Evidence
from trigger_point.workflow.verification import audit_evidence

NOW = datetime(2026, 10, 31, tzinfo=UTC)
TODAY = date(2026, 10, 31)


def ev(**over: object) -> Evidence:
    base: dict[str, object] = {
        "id": "ev_1",
        "entity_type": "account",
        "entity_id": "1001",
        "claim": "Support role posted",
        "source_kind": "job_posting",
        "source_url": "https://jobs.example/1",
        "provider_ref": "crustdata:/job/search:1",
        "publisher": "Crustdata job index",
        "event_on": date(2026, 10, 23),
        "retrieved_at": NOW,
        "excerpt": "Support Specialist",
    }
    return Evidence.model_validate({**base, **over})


def test_sourced_dated_fresh_evidence_is_verified() -> None:
    check = audit_evidence(ev(), "1001", TODAY, NOW)
    assert check.status == "verified" and check.reasons == []
    assert check.method == "audit-v1"


def test_recorded_provider_id_is_an_acceptable_source() -> None:
    e = ev(source_url=None, event_on=None, as_of=date(2026, 10, 23), source_kind="provider_field")
    assert audit_evidence(e, "1001", TODAY, NOW).status == "verified"


def test_no_source_at_all_is_unverifiable() -> None:
    e = ev(source_url=None, provider_ref=None)
    check = audit_evidence(e, "1001", TODAY, NOW)
    assert check.status == "unverifiable" and "no_source" in check.reasons


def test_a_javascript_url_is_not_a_source() -> None:
    e = ev(source_url="javascript:alert(1)", provider_ref=None)
    assert audit_evidence(e, "1001", TODAY, NOW).status == "unverifiable"


def test_missing_excerpt_is_unverifiable() -> None:
    assert audit_evidence(ev(excerpt=None), "1001", TODAY, NOW).status == "unverifiable"


def test_wrong_entity_is_a_mismatch() -> None:
    assert audit_evidence(ev(entity_id="9"), "1001", TODAY, NOW).status == "entity_mismatch"


def test_person_evidence_is_tied_by_its_own_person_id() -> None:
    e = ev(entity_type="person", entity_id="77", source_kind="provider_profile")
    assert audit_evidence(e, "1001", TODAY, NOW, person_ids={"77"}).status == "verified"
    assert audit_evidence(e, "1001", TODAY, NOW).status == "entity_mismatch"


def test_older_than_policy_is_stale() -> None:
    e = ev(event_on=date(2026, 6, 4))
    check = audit_evidence(e, "1001", TODAY, NOW)
    assert check.status == "stale" and check.age_days == 149


def test_no_date_is_undated_and_retrieval_time_never_stands_in() -> None:
    assert audit_evidence(ev(event_on=None), "1001", TODAY, NOW).status == "undated"


def test_a_future_date_is_not_verified() -> None:
    check = audit_evidence(ev(event_on=date(2026, 11, 5)), "1001", TODAY, NOW)
    assert check.status == "unverifiable" and "future_date" in check.reasons
