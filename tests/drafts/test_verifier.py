from typing import Any

import pytest

from tests.cases.test_case_builder import approved_context, research
from tests.research.factories import NOW, TODAY
from trigger_point.cases.builder import build_case
from trigger_point.cases.models import AccountCase
from trigger_point.drafts.models import DraftClaim, DraftWire, FollowUpStep
from trigger_point.drafts.verifier import verify_draft


@pytest.fixture
def case() -> AccountCase:
    ar, p = research()
    return build_case(ar, p, approved_context(), "ctx1", "r1", TODAY, NOW, "replay")


def ids(case: AccountCase) -> dict[str, str]:
    job = next(
        e.id
        for e in case.evidence
        if e.source_kind == "job_posting" and e.id in case.hook_evidence_ids
    )
    proof = next(e.id for e in case.evidence if e.entity_type == "seller" and "45%" in e.claim)
    person = next(e.id for e in case.evidence if e.entity_type == "person")
    # Firmographic profile evidence: a fact about the account, never a why-now hook.
    account = next(e.id for e in case.evidence if "employees" in e.claim)
    return {"job": job, "proof": proof, "person": person, "account": account}


BODY = (
    "Hi Ana,\n\nLedgerloop posted a Customer Support Specialist role on 2026-10-15. Teams adding "
    "support headcount often look at deflecting repetitive tickets first. Acme resolves up to "
    "45% of inbound tickets for SaaS support teams. Would a 20-minute call next week be "
    "useful?\n\n[Your name]"
)


def wire(case: AccountCase, **over: Any) -> DraftWire:
    i = ids(case)
    base: dict[str, Any] = dict(
        subject="Support hiring at Ledgerloop",
        body=BODY,
        hook_evidence_id=i["job"],
        proof_point_evidence_id=i["proof"],
        claims=[
            DraftClaim(
                text="Ledgerloop posted a Customer Support Specialist role on 2026-10-15",
                kind="fact",
                evidence_ids=[i["job"]],
            ),
            DraftClaim(
                text="Teams adding support headcount often look at deflection first",
                kind="inference",
                evidence_ids=[],
            ),
            DraftClaim(
                text="Acme resolves up to 45% of inbound tickets",
                kind="fact",
                evidence_ids=[i["proof"]],
            ),
        ],
        follow_ups=[
            FollowUpStep(
                day_offset=4, angle="Native Zendesk integration", evidence_ids=[i["proof"]]
            )
        ],
    )
    base.update(over)
    return DraftWire(**base)


def codes(findings: list) -> set[str]:  # type: ignore[type-arg]
    return {f.code for f in findings if f.severity == "error"}


def test_grounded_draft_passes(case: AccountCase) -> None:
    findings = verify_draft(wire(case), case, other_account_names=["Quartzdesk"])
    assert codes(findings) == set(), findings


def test_invented_number_fails(case: AccountCase) -> None:
    body = BODY.replace("up to 45%", "60%")
    assert "unsupported_number" in codes(verify_draft(wire(case, body=body), case, []))


def test_meeting_length_is_not_a_claim(case: AccountCase) -> None:
    assert "unsupported_number" not in codes(verify_draft(wire(case), case, []))


def test_hook_must_be_an_active_case_hook(case: AccountCase) -> None:
    w = wire(case, hook_evidence_id=ids(case)["account"])
    assert "invalid_hook" in codes(verify_draft(w, case, []))


def test_uncited_fact_and_unknown_evidence_fail(case: AccountCase) -> None:
    w = wire(
        case,
        claims=[
            DraftClaim(text="Ledgerloop doubled revenue", kind="fact", evidence_ids=[]),
            DraftClaim(text="x", kind="fact", evidence_ids=["ev_made_up"]),
        ],
    )
    assert {"uncited_fact", "unknown_evidence"} <= codes(verify_draft(w, case, []))


def test_proof_point_must_be_seller_evidence(case: AccountCase) -> None:
    w = wire(case, proof_point_evidence_id=ids(case)["account"])
    assert "invalid_proof_point" in codes(verify_draft(w, case, []))


def test_other_prospect_name_is_wrong_entity(case: AccountCase) -> None:
    w = wire(case, body=BODY.replace("Teams adding", "Like Quartzdesk, teams adding"))
    assert "wrong_entity" in codes(verify_draft(w, case, ["Quartzdesk"]))


@pytest.mark.parametrize(
    ("phrase", "code"),
    [
        ("I hope this finds you well. ", "banned_phrase"),
        ("Our mutual connection suggested I reach out. ", "fake_familiarity"),
        ("As we discussed, ", "fake_familiarity"),
    ],
)
def test_banned_and_fake_familiarity_phrases(case: AccountCase, phrase: str, code: str) -> None:
    w = wire(case, body=BODY.replace("Ledgerloop posted", phrase + "Ledgerloop posted"))
    assert code in codes(verify_draft(w, case, []))


def test_too_long_fails(case: AccountCase) -> None:
    w = wire(case, body=BODY + " More words here." * 30)
    assert "too_long" in codes(verify_draft(w, case, []))


@pytest.mark.parametrize("ph", ["{first_name}", "[Company]", "<<name>>"])
def test_unfilled_placeholders_fail_but_sign_off_is_allowed(case: AccountCase, ph: str) -> None:
    assert "placeholder" in codes(verify_draft(wire(case, body=BODY.replace("Ana", ph)), case, []))
    assert "placeholder" not in codes(verify_draft(wire(case), case, []))


def test_contact_details_in_copy_fail(case: AccountCase) -> None:
    w = wire(case, body=BODY + " Reach me at ana@ledgerloop.example or +1 415 555 0100.")
    assert "private_data" in codes(verify_draft(w, case, []))


def test_non_contactable_route_fails(case: AccountCase) -> None:
    blocked = case.model_copy(update={"recommended_route": "do_not_contact", "recipient": None})
    assert "not_contactable" in codes(verify_draft(wire(case), blocked, []))


def test_missing_ask_is_a_warning(case: AccountCase) -> None:
    w = wire(case, body=BODY.replace("Would a 20-minute call next week be useful?", "Thanks."))
    findings = verify_draft(w, case, [])
    assert any(f.code == "missing_ask" and f.severity == "warning" for f in findings)


def test_follow_up_must_cite_case_evidence(case: AccountCase) -> None:
    w = wire(case, follow_ups=[FollowUpStep(day_offset=3, angle="x", evidence_ids=["ev_nope"])])
    assert "unknown_evidence" in codes(verify_draft(w, case, []))


@pytest.mark.parametrize(
    "phrase",
    ["last month", "last week", "yesterday", "3 days ago", "a few weeks ago", "earlier this month"],
)
def test_past_relative_time_is_rejected(case: AccountCase, phrase: str) -> None:
    w = wire(case, body=BODY.replace("on 2026-10-15", phrase))
    assert "relative_time" in codes(verify_draft(w, case, []))


def test_future_ask_timing_is_allowed(case: AccountCase) -> None:
    assert "relative_time" not in codes(verify_draft(wire(case), case, []))  # "next week"


def test_i_noticed_opener_is_banned(case: AccountCase) -> None:
    w = wire(case, body=BODY.replace("Ledgerloop posted", "I noticed Ledgerloop posted"))
    assert "banned_phrase" in codes(verify_draft(w, case, []))


def test_unused_hook_is_a_warning(case: AccountCase) -> None:
    body = BODY.replace("Ledgerloop posted a Customer Support Specialist role on 2026-10-15. ", "")
    findings = verify_draft(wire(case, body=body), case, [])
    assert any(f.code == "hook_not_used" and f.severity == "warning" for f in findings)
