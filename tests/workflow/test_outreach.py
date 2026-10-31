"""Outreach to targets the user names: one audience, one purpose, verified, approved, never sent."""

from typing import Any

import pytest

from tests.workflow.conftest import GOAL, URL, Rig
from trigger_point.workflow.outreach import AUDIENCES, OutreachWire, verify_outreach
from trigger_point.workflow.outreach import content_hash as outreach_hash

FACTS = ["Your child's first topic is free.", "Built by IIT Bombay founders."]


def wire(**over: Any) -> OutreachWire:
    base = {
        "subject": "A maths pilot",
        "body": "We would like to discuss a pilot.",
        "claims": [],
    }
    return OutreachWire.model_validate({**base, **over})


def codes(w: OutreachWire, notes: str = "") -> list[str]:
    return [
        f.code
        for f in verify_outreach(w, FACTS, "St Mary's School", notes)
        if f.severity == "error"
    ]


def test_a_plain_honest_message_passes() -> None:
    assert codes(wire()) == []


def test_a_number_nobody_approved_is_rejected() -> None:
    assert "unsupported_number" in codes(wire(body="Students improve 40% in a term."))


def test_a_number_from_the_users_own_notes_is_allowed() -> None:
    assert codes(wire(body="For your 1200 students."), notes="1200 students") == []


def test_fake_familiarity_is_rejected() -> None:
    assert "fake_familiarity" in codes(wire(body="Our mutual friend suggested this."))
    assert "banned_phrase" in codes(wire(body="I noticed your school is growing."))


def test_contact_data_is_rejected() -> None:
    assert "contact_data" in codes(wire(body="Write to jane@school.example"))


def test_an_unfilled_placeholder_is_rejected() -> None:
    assert "placeholder" in codes(wire(body="Dear {name}, hello."))


def test_a_message_that_is_too_long_is_rejected() -> None:
    assert "too_long" in codes(wire(body="word " * 400))


def ready(rig: Rig, goal: str = GOAL) -> str:
    mid = str(rig.call("create_mission", website_url=URL, goal=goal)["mission_id"])
    a = rig.call("request_user_approval", mission_id=mid, gate="business_profile")
    rig.call(
        "approve_business_profile",
        mission_id=mid,
        approval_id=a["approval_id"],
        acknowledge_unsupported=True,
    )
    return mid


def test_a_target_is_a_user_statement_not_a_discovered_fact(rig: Rig) -> None:
    mid = ready(rig)
    t = rig.services.workflow.add_target(
        mid, {"name": "St Mary's School", "audience": "school_authority"}
    )
    assert t["ok"] and rig.services.workflow.targets(mid)[0]["source"] == "user"


def test_an_unknown_audience_is_refused(rig: Rig) -> None:
    mid = ready(rig)
    assert (
        rig.services.workflow.add_target(mid, {"name": "x", "audience": "everyone"})["ok"] is False
    )


def test_writing_needs_the_approved_profile(rig: Rig) -> None:
    mid = str(rig.call("create_mission", website_url=URL, goal=GOAL)["mission_id"])
    t = rig.services.workflow.add_target(mid, {"name": "A", "audience": "school_authority"})
    assert rig.services.workflow.write_outreach(mid, t["id"])["error"] == "approval_missing"


def test_each_audience_has_a_purpose_and_an_ask() -> None:
    assert {"school_authority", "parent"} <= set(AUDIENCES)
    assert all(a.purpose and a.ask for a in AUDIENCES.values())


@pytest.mark.parametrize("audience", ["school_authority", "parent"])
def test_a_written_message_is_verified_and_never_sent(rig: Rig, audience: str) -> None:
    mid = ready(rig)
    wf = rig.services.workflow
    t = wf.add_target(mid, {"name": "Sunrise", "audience": audience})
    d = wf.write_outreach(mid, t["id"])
    assert d["ok"] and d["status"] == "verified" and d["sending"] == "disabled"
    assert d["mode"] == "replay" and d["prompt_version"]


def test_approval_is_bound_to_the_exact_text(rig: Rig) -> None:
    mid = ready(rig)
    wf = rig.services.workflow
    t = wf.add_target(mid, {"name": "Sunrise", "audience": "parent"})
    d = wf.write_outreach(mid, t["id"])
    assert wf.approve_outreach(mid, d["id"], "0" * 64)["ok"] is False
    assert wf.approve_outreach(mid, d["id"], d["content_hash"])["status"] == "approved"
    assert wf.outreach(mid)[0]["sending"] == "disabled"


def test_an_edit_needs_the_verifier_and_a_new_approval(rig: Rig) -> None:
    mid = ready(rig)
    wf = rig.services.workflow
    t = wf.add_target(mid, {"name": "Sunrise", "audience": "parent"})
    d = wf.write_outreach(mid, t["id"])
    wf.approve_outreach(mid, d["id"], d["content_hash"])
    bad = wf.edit_outreach(mid, d["id"], d["subject"], "Scores rise 90% in a week.")
    assert bad["status"] == "rejected"
    assert bad["content_hash"] != d["content_hash"]
    assert wf.approve_outreach(mid, d["id"], bad["content_hash"])["ok"] is False


def test_rewriting_a_target_replaces_nothing_silently(rig: Rig) -> None:
    mid = ready(rig)
    wf = rig.services.workflow
    t = wf.add_target(mid, {"name": "Sunrise", "audience": "parent"})
    wf.write_outreach(mid, t["id"])
    wf.write_outreach(mid, t["id"])
    assert len(wf.outreach(mid)) == 2


def test_a_number_followed_by_punctuation_is_still_that_number() -> None:
    assert codes(wire(body="For Classes 6–10, built on NCERT."), notes="Classes 6 to 10") == []


def test_claiming_a_pilot_is_running_needs_an_approved_fact() -> None:
    body = "We are currently running a small pilot with first families in Mumbai."
    assert "unsupported_traction" in codes(wire(body=body))
    allowed = [
        f
        for f in verify_outreach(wire(body=body), ["We run a pilot with first families."], "x")
        if f.code == "unsupported_traction"
    ]
    assert allowed == []


def test_proposing_a_pilot_is_not_a_claim_of_traction() -> None:
    assert codes(wire(body="Could we discuss a small pilot with your school?")) == []


@pytest.mark.parametrize(
    "body",
    [
        "We already work with several schools.",
        "Hundreds of students use Tulip.",
        "Schools across Mumbai trust us.",
        "Parents love the results.",
    ],
)
def test_invented_traction_is_rejected(body: str) -> None:
    assert "unsupported_traction" in codes(wire(body=body))


TEST_INBOX = "inbox@example.test"


def prepared(rig: Rig) -> tuple[Any, str, dict[str, Any]]:
    wf = rig.services.workflow
    wf.test_recipients = (TEST_INBOX,)
    mid = ready(rig)
    t = wf.add_target(mid, {"name": "Sunrise", "audience": "parent"})
    return wf, mid, wf.write_outreach(mid, t["id"])


def test_samples_are_labelled_and_can_be_added_once(rig: Rig) -> None:
    mid = ready(rig)
    wf = rig.services.workflow
    wf.add_sample_targets(mid)
    wf.add_sample_targets(mid)
    targets = wf.targets(mid)
    assert len(targets) == 4 and all(t["name"].startswith("SAMPLE") for t in targets)
    assert {t["audience"] for t in targets} == {"school_authority", "parent"}


def test_a_test_send_goes_only_to_the_test_inbox_and_is_marked(rig: Rig) -> None:
    wf, mid, d = prepared(rig)
    out = wf.prepare_test_send(mid, d["id"])
    assert out["to"] == [TEST_INBOX] and out["subject"].startswith("[Trigger Point test]")
    assert "not contacted" in out["body"]


def test_a_rejected_draft_cannot_be_test_sent(rig: Rig) -> None:
    wf, mid, d = prepared(rig)
    bad = wf.edit_outreach(mid, d["id"], d["subject"], "Scores rise 90% in a week.")
    assert wf.prepare_test_send(mid, bad["id"])["ok"] is False


def passed_under_older_rules(wf: Any, mid: str, d: dict[str, Any]) -> dict[str, Any]:
    """Stored as verified, but today's rules would reject it."""
    stale = {**d, "body": "Scores rise 90% in a week."}
    stale.pop("ok", None)
    stale["content_hash"] = outreach_hash(d["target_id"], d["subject"], stale["body"])
    wf.engine.save_record("outreach", d["id"], mid, stale)
    return stale


def test_a_stale_verified_draft_cannot_be_test_sent(rig: Rig) -> None:
    wf, mid, d = prepared(rig)
    stale = passed_under_older_rules(wf, mid, d)
    assert wf.prepare_test_send(mid, stale["id"])["error"] == "not_verified"
    assert wf.outreach(mid)[0]["status"] == "rejected"


def test_a_stale_verified_draft_cannot_be_approved(rig: Rig) -> None:
    wf, mid, d = prepared(rig)
    stale = passed_under_older_rules(wf, mid, d)
    assert wf.approve_outreach(mid, stale["id"], stale["content_hash"])["ok"] is False
    assert wf.outreach(mid)[0]["status"] == "rejected"


def test_an_approved_draft_that_still_passes_stays_approved(rig: Rig) -> None:
    wf, mid, d = prepared(rig)
    wf.approve_outreach(mid, d["id"], d["content_hash"])
    assert wf.prepare_test_send(mid, d["id"])["ok"] is True
    assert wf.outreach(mid)[0]["status"] == "approved"


def test_with_no_allowlist_nothing_can_be_prepared(rig: Rig) -> None:
    wf, mid, d = prepared(rig)
    wf.test_recipients = ()
    assert wf.prepare_test_send(mid, d["id"])["error"] == "no_test_inbox"


def test_a_send_is_recorded_and_stays_separate_from_approval(rig: Rig) -> None:
    wf, mid, d = prepared(rig)
    out = wf.record_test_send(mid, d["id"], TEST_INBOX, "msg1", "thr1")
    assert out["ok"]
    record = wf.outreach(mid)[0]
    assert record["status"] == "verified" and record["sending"] == "disabled"
    assert record["test_sends"][0]["message_id"] == "msg1"


def test_a_send_to_anyone_else_cannot_be_recorded(rig: Rig) -> None:
    wf, mid, d = prepared(rig)
    assert wf.record_test_send(mid, d["id"], "a@b.example", "m", "t")["ok"] is False


def test_a_booked_test_meeting_never_teaches(rig: Rig) -> None:
    wf, mid, _ = prepared(rig)
    out = wf.record_test_meeting(
        mid,
        {
            "title": "Pilot",
            "held_on": "2026-11-06",
            "account_name": "SAMPLE",
            "event_id": "e1",
            "link": "https://meet.google.com/x",
        },
    )
    assert out["ok"]
    o = wf.outcomes(mid)[0]
    assert o.kind == "meeting_booked" and o.mode == "test"
    assert wf.meetings(mid)[0]["source"] == "google_calendar"


def test_a_missing_fixture_is_retryable_not_the_end_of_the_mission(rig: Rig) -> None:
    from tests.workflow.conftest import advance_to_accounts

    mid = advance_to_accounts(rig)

    def missing(_r: Any) -> None:
        from trigger_point.providers.crustdata.replay import ReplayMissing

        raise ReplayMissing("no fixture")

    rig.provider.answer = missing  # type: ignore[assignment]
    out = rig.call("discover_accounts", mission_id=mid)
    assert out["ok"] is False and out["state"] == "NEEDS_RETRY"


@pytest.mark.parametrize(
    "body",
    [
        "Hello, this is Prateek from Tulip.",
        "My name is Som.",
        "I am Rahul from Tulip.",
        "I'm Priya, a founder at Tulip.",
        "Regards,\nAnita",
    ],
)
def test_an_invented_sender_is_rejected(body: str) -> None:
    assert "invented_person" in codes(wire(body=body))


def test_a_person_named_in_the_facts_may_sign() -> None:
    found = verify_outreach(wire(body="Hello, this is Som from Tulip."), ["Founded by Som."], "x")
    assert "invented_person" not in [f.code for f in found]


def test_signing_as_the_company_is_fine() -> None:
    assert codes(wire(body="Regards,\nTulip"), notes="Tulip") == []
    assert codes(wire(body="I am writing from Tulip about a pilot."), notes="Tulip") == []
