"""The learning loop's pure rules: what counts, what is too small, what a result means."""

from datetime import date, timedelta

import pytest

from trigger_point.workflow.gtm import MIN_SAMPLE, Outcome
from trigger_point.workflow.loop import (
    MATURITY_DAYS,
    Touch,
    classify_reply,
    compare,
    lifecycle,
    measure,
    parse_gmail_messages,
    parse_meeting,
    quote_found,
    unwrap_tool_response,
)

TODAY = date(2026, 6, 30)
OLD = TODAY - timedelta(days=MATURITY_DAYS + 1)


def touch(i: int, audience: str = "parent", **over: object) -> Touch:
    return Touch.model_validate(
        {
            "id": f"t{i}",
            "account_name": f"Account {i}",
            "audience": audience,
            "sent_on": OLD,
            "mode": "live",
            **over,
        }
    )


def won(t: Touch, kind: str = "meeting_booked", mode: str = "live") -> Outcome:
    return Outcome(
        id=f"o{t.id}",
        mission_id="m",
        account_name=t.account_name,
        kind=kind,  # type: ignore[arg-type]
        occurred_on=TODAY,
        mode=mode,
        outreach_id=t.id,
    )


def groups(touches: list[Touch], outcomes: list[Outcome]) -> dict[str, dict[str, object]]:
    report = compare(touches, outcomes, TODAY, ("live",))
    return {f"{g['dimension']}:{g['value']}": g for g in report["groups"]}


def test_the_mcp_wrapper_is_removed_from_a_hook_response() -> None:
    assert unwrap_tool_response([{"type": "text", "text": '{"id": "1"}'}]) == {"id": "1"}
    assert unwrap_tool_response('{"id": "1"}') == {"id": "1"}
    assert unwrap_tool_response({"id": "1"}) == {"id": "1"}
    assert unwrap_tool_response({"content": [{"type": "text", "text": '{"id": "1"}'}]}) == {
        "id": "1"
    }
    assert unwrap_tool_response("not json") is None


def test_a_gmail_thread_separates_our_mail_from_theirs() -> None:
    messages = parse_gmail_messages(
        {
            "messages": [
                {"id": "a", "sender": "us@x.test", "labelIds": ["SENT"], "plaintextBody": "Hi"},
                {
                    "id": "b",
                    "sender": "them@y.test",
                    "labelIds": ["INBOX"],
                    "date": "2026-06-29T10:00:00Z",
                    "plaintextBody": "Sounds good",
                },
            ]
        }
    )
    assert [m.id for m in messages if not m.ours] == ["b"]
    assert messages[1].received_on == date(2026, 6, 29)


def test_a_meeting_is_parsed_from_what_wispr_returned() -> None:
    m = parse_meeting(
        {
            "id": "w1",
            "title": "Sunrise pilot",
            "summary": "Next steps",
            "content": "notes",
            "transcript": "Principal: fees are the problem",
            "attendees": ["Asha"],
            "start": "2026-06-01T09:00:00Z",
            "share_link": "https://notes.wisprflow.ai/shared/x",
        }
    )
    assert m is not None and m.title == "Sunrise pilot" and m.held_on == date(2026, 6, 1)
    assert "fees are the problem" in m.text
    assert parse_meeting({"nope": 1}) is None


@pytest.mark.parametrize(
    ("sender", "body", "kind"),
    [
        ("mailer-daemon@googlemail.com", "Address not found", "bounced"),
        ("x@y.test", "Please unsubscribe me", "opted_out"),
        ("x@y.test", "Stop emailing me", "opted_out"),
        ("x@y.test", "Please remove me from your list", "opted_out"),
        ("x@y.test", "Yes, tell me more", "reply"),
        ("x@y.test", "We never stop learning here", "reply"),
    ],
)
def test_replies_are_classified_by_rule(sender: str, body: str, kind: str) -> None:
    assert classify_reply(sender, body) == kind


def test_a_quote_must_exist_in_the_source_ignoring_only_spacing_and_case() -> None:
    text = "Principal:  fees are\nthe main problem for us"
    assert quote_found("fees are the main problem", text)
    assert quote_found("FEES are the main problem", text)
    assert not quote_found("fees are the only problem", text)
    assert not quote_found("   ", text)


def test_lifecycle_never_infers_a_later_state() -> None:
    draft = {"status": "verified"}
    assert lifecycle(draft, [], [])["state"] == "verified"
    sent = {**draft, "test_sends": [{"to": "a", "message_id": "1"}]}
    assert lifecycle(sent, [], [])["state"] == "sent"
    replied = lifecycle(sent, [{"kind": "reply"}], [])
    assert replied["state"] == "replied" and "booked" not in replied["reached"]
    assert lifecycle(sent, [{"kind": "reply"}], [{"id": "m"}])["state"] == "booked"
    assert lifecycle(sent, [{"kind": "bounced"}], [])["state"] == "bounced"
    planned = {**draft, "schedule": {"state": "scheduled"}}
    assert lifecycle(planned, [], [])["state"] == "scheduled"


def test_a_meeting_does_not_make_an_unsent_message_booked() -> None:
    assert lifecycle({"status": "verified"}, [], [{"id": "m"}])["state"] == "verified"


def test_rates_use_touches_as_the_denominator() -> None:
    touches = [touch(i) for i in range(MIN_SAMPLE)]
    got = groups(touches, [won(touches[0]), won(touches[1])])["audience:parent"]
    assert got["n"] == MIN_SAMPLE and got["wins"] == 2 and got["rate"] == 0.4


def test_a_small_group_is_marked_too_small() -> None:
    touches = [touch(i) for i in range(MIN_SAMPLE - 1)]
    assert groups(touches, [])["audience:parent"]["enough"] is False


def test_test_and_fixture_touches_do_not_count() -> None:
    touches = [touch(1, mode="test"), touch(2, mode="replay"), touch(3)]
    report = compare(touches, [], TODAY, ("live",))
    assert report["counted"] == 1 and report["excluded"] == 2


def test_a_recent_send_is_pending_not_a_failure() -> None:
    touches = [touch(1, sent_on=TODAY), touch(2)]
    report = compare(touches, [], TODAY, ("live",))
    assert report["pending"] == 1 and report["counted"] == 1


def test_a_recent_send_that_already_won_is_counted() -> None:
    fresh = touch(1, sent_on=TODAY)
    report = compare([fresh], [won(fresh)], TODAY, ("live",))
    assert report["pending"] == 0 and report["counted"] == 1


def test_an_outcome_with_no_send_is_an_attribution_gap() -> None:
    stray = won(touch(99))
    report = compare([touch(1)], [stray], TODAY, ("live",))
    assert report["attribution_gaps"] == 1


def test_a_better_group_is_proposed_with_its_caveats() -> None:
    a = [touch(i, "school_authority") for i in range(MIN_SAMPLE)]
    b = [touch(i + 100, "parent") for i in range(MIN_SAMPLE)]
    report = compare([*a, *b], [won(t) for t in a[:3]], TODAY, ("live",))
    p = next(x for x in report["proposals"] if x["dimension"] == "audience")
    assert p["value"] == "school_authority" and p["rate"] == 0.6 and p["baseline"] == 0.0
    assert p["target"] == "icp" and p["checks"]["selection_bias"] is True
    assert "correlation" in p["caveat"].lower()


def test_nothing_is_proposed_from_small_groups() -> None:
    a = [touch(i, "school_authority") for i in range(2)]
    b = [touch(i + 100, "parent") for i in range(2)]
    assert compare([*a, *b], [won(a[0])], TODAY, ("live",))["proposals"] == []


def test_measure_waits_for_enough_on_both_sides() -> None:
    assert measure(0.5, 3, 0.1, 50)["verdict"] == "insufficient"
    assert measure(0.5, 50, 0.1, 3)["verdict"] == "insufficient"


@pytest.mark.parametrize(
    ("after", "before", "verdict", "action"),
    [
        (0.5, 0.2, "improved", "keep"),
        (0.2, 0.5, "worse", "roll_back"),
        (0.21, 0.2, "no_change", "keep_watching"),
    ],
)
def test_measure_says_what_the_numbers_support(
    after: float, before: float, verdict: str, action: str
) -> None:
    got = measure(after, 10, before, 10)
    assert got["verdict"] == verdict and got["action"] == action
