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
    split_cut,
    strip_quoted,
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


def test_a_send_counts_under_every_signal_that_justified_it() -> None:
    both = [touch(i, signal_types=["topic_engagement", "active_hiring"]) for i in range(MIN_SAMPLE)]
    got = groups(both, [])
    assert got["signal_type:topic_engagement"]["n"] == MIN_SAMPLE
    assert got["signal_type:active_hiring"]["n"] == MIN_SAMPLE


def test_a_better_signal_is_proposed_by_name_for_qualification() -> None:
    topic = [touch(i, signal_types=["topic_engagement"]) for i in range(MIN_SAMPLE)]
    hiring = [touch(i + 100, signal_types=["active_hiring"]) for i in range(MIN_SAMPLE)]
    report = compare([*topic, *hiring], [won(t) for t in topic[:3]], TODAY, ("live",))
    p = next(x for x in report["proposals"] if x["dimension"] == "signal_type")
    assert p["value"] == "topic_engagement" and p["target"] == "qualification"
    assert p["rate"] == 0.6 and p["baseline"] == 0.0


def test_a_touch_with_two_signals_does_not_pollute_its_own_baseline() -> None:
    # Five touches carry both signals and win; five carry only hiring and lose. Topic engagement
    # is on the winners only, so its baseline must be the hiring-only touches, not the winners.
    both = [touch(i, signal_types=["topic_engagement", "active_hiring"]) for i in range(MIN_SAMPLE)]
    hiring_only = [touch(i + 100, signal_types=["active_hiring"]) for i in range(MIN_SAMPLE)]
    report = compare([*both, *hiring_only], [won(t) for t in both], TODAY, ("live",))
    p = next(x for x in report["proposals"] if x["value"] == "topic_engagement")
    assert p["rate"] == 1.0 and p["baseline"] == 0.0


def test_touches_with_no_signal_are_simply_not_in_a_signal_group() -> None:
    plain = [touch(i) for i in range(MIN_SAMPLE)]
    assert not [
        g for g in compare(plain, [], TODAY, ("live",))["groups"] if g["dimension"] == "signal_type"
    ]


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


REAL_CUT = "(...truncated, 5580 chars remaining; continue with view_transcript.start_char=12000...)"


def test_the_real_wispr_cut_marker_is_found_even_inside_its_end_fence() -> None:
    # Seen on a real account: the marker is followed by a fence line, not the end of the text.
    text, start = split_cut(f"Head: we talked.\n{REAL_CUT}\n<<<END TRANSCRIPT>>>")
    assert start == 12000 and "truncated" not in text and "<<<" not in text
    assert text.strip() == "Head: we talked."


def test_a_complete_transcript_inside_fences_is_clean_and_not_cut() -> None:
    text, start = split_cut("<<<BEGIN TRANSCRIPT>>>\nA: hello\n<<<END TRANSCRIPT>>>")
    assert start is None and text.strip() == "A: hello"


QUOTE = "On Sat, 31 Oct 2026 at 11:00, Anmol <anmol@x.test> wrote:\n> Dear Principal,\n> reply STOP to unsubscribe"


def test_only_what_the_person_wrote_is_kept_not_the_quoted_original() -> None:
    assert strip_quoted(f"Yes, tell me more\n\n{QUOTE}") == "Yes, tell me more"


def test_a_header_that_wraps_over_two_lines_is_still_cut() -> None:
    wrapped = (
        "Sounds good\n\nOn Sat, 31 Oct 2026 at 11:00, Anmol Sureka\n<anmol@x.test> wrote:\n> hi"
    )
    assert strip_quoted(wrapped) == "Sounds good"


def test_inline_quoted_lines_are_dropped_and_the_answer_kept() -> None:
    inline = (
        "> Would you like a pilot?\nYes, in Class 8\n> reply STOP to unsubscribe\nNot before March"
    )
    assert strip_quoted(inline) == "Yes, in Class 8\nNot before March"


def test_a_reply_with_no_quote_is_unchanged() -> None:
    assert strip_quoted("Please unsubscribe me") == "Please unsubscribe me"


def test_a_quoted_unsubscribe_in_our_own_text_is_not_an_opt_out() -> None:
    body = strip_quoted(f"Yes, tell me more\n\n{QUOTE}")
    assert classify_reply("person@x.test", body) == "reply"


def test_the_gmail_parser_strips_the_quote_before_anything_reads_the_body() -> None:
    m = parse_gmail_messages(
        {
            "messages": [
                {
                    "id": "b",
                    "sender": "them@y.test",
                    "labelIds": ["INBOX"],
                    "plaintextBody": f"Great\n\n{QUOTE}",
                }
            ]
        }
    )
    assert m[0].body == "Great"


def test_an_untitled_recording_is_still_a_meeting_and_says_so() -> None:
    m = parse_meeting(
        {"id": "m9", "title": "", "start": "2026-10-04T16:51:28Z", "transcript": "hi"}
    )
    assert m is not None and m.title == "Untitled meeting on 2026-10-04"


def test_a_recording_with_no_id_is_not_a_meeting() -> None:
    assert parse_meeting({"title": "x"}) is None
