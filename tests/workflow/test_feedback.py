"""Replies, schedules, meetings and the closed loop, through the real services over fixtures."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from tests.workflow.conftest import Rig
from tests.workflow.test_outreach import TEST_INBOX, prepared, ready
from trigger_point.workflow.feedback import FeedbackService
from trigger_point.workflow.gtm import MIN_SAMPLE
from trigger_point.workflow.loop import MATURITY_DAYS, Touch

GET_THREAD = "mcp__claude_ai_Gmail__get_thread"
GET_MEETING = "mcp__claude_ai_Wispr_Flow__get_meeting"
TRANSCRIPT = "Principal: the fees are the main problem. Teacher: we would pilot Class 8 first."


def sent(rig: Rig) -> tuple[FeedbackService, str, dict[str, Any]]:
    wf, mid, d = prepared(rig)
    wf.record_test_send(mid, d["id"], TEST_INBOX, "m1", "t1")
    return rig.services.feedback, mid, wf.outreach(mid)[0]


def capture_reply(fb: FeedbackService, mid: str, body: str, sender: str = "them@x.test") -> None:
    fb.capture(
        mid,
        GET_THREAD,
        {"threadId": "t1"},
        [
            {
                "type": "text",
                "text": (
                    '{"id": "t1", "messages": ['
                    '{"id": "m1", "threadId": "t1", "labelIds": ["SENT"], "sender": "us@x.test"},'
                    f'{{"id": "m2", "threadId": "t1", "labelIds": ["INBOX"], "sender": "{sender}",'
                    f'"date": "2026-06-01T10:00:00Z", "plaintextBody": "{body}"}}]}}'
                ),
            }
        ],
    )


def capture_meeting(fb: FeedbackService, mid: str, title: str = "Sunrise pilot") -> None:
    fb.capture(
        mid,
        GET_MEETING,
        {"meeting_id": "w1", "view_transcript": {}},
        {
            "id": "w1",
            "title": title,
            "transcript": TRANSCRIPT,
            "summary": "Pilot talk",
            "attendees": ["Asha"],
            "start": "2026-06-01T09:00:00Z",
            "share_link": "https://notes.wisprflow.ai/shared/x",
        },
    )


def imported(rig: Rig) -> tuple[FeedbackService, str, str]:
    fb, mid, _ = sent(rig)
    capture_meeting(fb, mid)
    return fb, mid, fb.import_meeting(mid, "w1")["id"]


def test_only_read_tools_are_captured(rig: Rig) -> None:
    fb, mid, _ = sent(rig)
    assert fb.capture(mid, "mcp__claude_ai_Gmail__send_message", {}, {"id": "x"})["ok"] is False


def test_a_reply_comes_from_the_captured_thread_and_is_counted_once(rig: Rig) -> None:
    fb, mid, _ = sent(rig)
    capture_reply(fb, mid, "Yes, tell me more")
    assert fb.sync_replies(mid)["added"] == 1
    assert fb.sync_replies(mid)["added"] == 0
    reply = fb.replies(mid)[0]
    assert reply["kind"] == "reply" and reply["sender"] == "them@x.test"
    outcome = rig.services.workflow.outcomes(mid)[0]
    assert outcome.kind == "reply" and outcome.mode == "test"


def test_a_thread_we_never_sent_is_ignored(rig: Rig) -> None:
    fb, mid, _ = sent(rig)
    fb.capture(
        mid,
        GET_THREAD,
        {"threadId": "other"},
        {"id": "other", "messages": [{"id": "z", "threadId": "other", "labelIds": ["INBOX"]}]},
    )
    assert fb.sync_replies(mid)["added"] == 0


def test_an_opt_out_suppresses_the_target_and_stops_sending(rig: Rig) -> None:
    fb, mid, o = sent(rig)
    capture_reply(fb, mid, "Please unsubscribe me")
    fb.sync_replies(mid)
    assert fb.suppressions(mid)[0]["reason"] == "opted_out"
    assert rig.services.workflow.prepare_test_send(mid, o["id"])["error"] == "suppressed"
    assert fb.write_follow_up(mid, o["id"])["ok"] is False


def test_a_bounce_is_recorded_as_a_bounce(rig: Rig) -> None:
    fb, mid, _ = sent(rig)
    capture_reply(fb, mid, "Address not found", "mailer-daemon@googlemail.com")
    fb.sync_replies(mid)
    assert rig.services.workflow.outcomes(mid)[0].kind == "bounced"


def test_interest_is_a_persons_call(rig: Rig) -> None:
    fb, mid, _ = sent(rig)
    capture_reply(fb, mid, "Yes, tell me more")
    fb.sync_replies(mid)
    assert "positive_reply" not in [o.kind for o in rig.services.workflow.outcomes(mid)]
    fb.label_reply(mid, "m2", "positive")
    assert "positive_reply" in [o.kind for o in rig.services.workflow.outcomes(mid)]


def scheduled(rig: Rig, hours: int = 2) -> tuple[FeedbackService, str, str]:
    wf, mid, d = prepared(rig)
    fb = rig.services.feedback
    when = (datetime.now(UTC) + timedelta(hours=hours)).replace(tzinfo=None).isoformat()
    assert fb.schedule_send(mid, d["id"], when, "UTC")["ok"]
    return fb, mid, d["id"]


def test_a_scheduled_message_shows_its_details(rig: Rig) -> None:
    fb, mid, oid = scheduled(rig)
    schedule = rig.services.workflow.outreach(mid)[0]["schedule"]
    assert schedule["timezone"] == "UTC" and schedule["recipient"] == "test inbox"
    assert schedule["state"] == "scheduled" and schedule["step"] == 1
    assert fb.view(mid)["lifecycle"][oid]["state"] == "scheduled"


def test_a_time_in_the_past_or_a_bad_timezone_is_refused(rig: Rig) -> None:
    wf, mid, d = prepared(rig)
    fb = rig.services.feedback
    assert fb.schedule_send(mid, d["id"], "2020-01-01T10:00:00", "UTC")["error"] == "bad_time"
    assert fb.schedule_send(mid, d["id"], "2999-01-01T10:00:00", "Mars/Base")["error"] == "bad_time"


def test_a_due_send_is_reported_once(rig: Rig) -> None:
    fb, mid, oid = scheduled(rig)
    fb.now = lambda: datetime.now(UTC) + timedelta(hours=2, minutes=1)
    assert fb.due_sends(mid) == [oid]
    assert fb.due_sends(mid) == []


def test_a_send_held_too_long_is_missed_never_sent_late(rig: Rig) -> None:
    fb, mid, oid = scheduled(rig)
    fb.now = lambda: datetime.now(UTC) + timedelta(hours=9)
    assert fb.due_sends(mid) == []
    assert rig.services.workflow.outreach(mid)[0]["schedule"]["state"] == "missed"


def test_recording_the_send_finishes_the_schedule(rig: Rig) -> None:
    fb, mid, oid = scheduled(rig)
    rig.services.workflow.record_test_send(mid, oid, TEST_INBOX, "m1", "t1")
    assert rig.services.workflow.outreach(mid)[0]["schedule"]["state"] == "sent"


def test_an_opt_out_cancels_what_was_scheduled(rig: Rig) -> None:
    fb, mid, oid = scheduled(rig)
    target = rig.services.workflow.targets(mid)[0]["id"]
    fb.suppress(mid, target, "asked by phone")
    assert rig.services.workflow.outreach(mid)[0]["schedule"]["state"] == "cancelled"


def test_the_same_text_cannot_be_scheduled_after_it_went(rig: Rig) -> None:
    fb, mid, o = sent(rig)
    got = fb.schedule_send(mid, o["id"], "2999-01-01T10:00:00", "UTC")
    assert got["error"] == "duplicate"


def test_a_follow_up_is_the_next_step_and_keeps_its_parent(rig: Rig) -> None:
    fb, mid, o = sent(rig)
    next_step = fb.write_follow_up(mid, o["id"])
    assert next_step["step"] == 2 and next_step["follow_up_of"] == o["id"]


def test_a_follow_up_needs_the_first_message_sent(rig: Rig) -> None:
    wf, mid, d = prepared(rig)
    assert rig.services.feedback.write_follow_up(mid, d["id"])["error"] == "not_sent"


def test_a_meeting_must_be_read_before_it_can_be_imported(rig: Rig) -> None:
    fb, mid, _ = sent(rig)
    assert fb.import_meeting(mid, "w1")["error"] == "not_read"


def test_a_meeting_naming_a_target_is_linked_and_counted(rig: Rig) -> None:
    fb, mid, mtg = imported(rig)
    meeting = rig.services.workflow.meetings(mid)[0]
    assert meeting["account_name"] == "Sunrise" and meeting["match_basis"] == "name"
    assert meeting["needs_review"] is False and meeting["has_transcript"] is True
    assert "transcript" not in meeting
    assert rig.services.workflow.outcomes(mid)[0].kind == "meeting_held"


CUT = "(...truncated, 40 chars remaining; continue with view_transcript.start_char=30...)"


def capture_part(fb: FeedbackService, mid: str, start: int, text: str) -> None:
    fb.capture(
        mid,
        GET_MEETING,
        {"meeting_id": "w2", "view_transcript": {"start_char": start}},
        {"id": "w2", "title": "Sunrise review", "transcript": text},
    )


def test_a_cut_off_transcript_must_be_read_to_the_end(rig: Rig) -> None:
    fb, mid, _ = sent(rig)
    capture_part(fb, mid, 0, f"Principal: the first half {CUT}")
    out = fb.import_meeting(mid, "w2")
    assert out["error"] == "incomplete" and out["continue_from"] == 30
    assert rig.services.workflow.meetings(mid) == []


def test_transcript_parts_join_without_the_marker(rig: Rig) -> None:
    fb, mid, _ = sent(rig)
    capture_part(fb, mid, 0, f"Principal: the first half {CUT}")
    capture_part(fb, mid, 30, "and the second half")
    mtg = fb.import_meeting(mid, "w2")["id"]
    out = fb.add_insights(
        mid,
        mtg,
        [
            {
                "kind": "pain",
                "text": "Spans the join",
                "basis": "statement",
                "quote": "the first half and the second half",
            },
            {"kind": "pain", "text": "Marker", "basis": "statement", "quote": "truncated, 40"},
        ],
    )
    assert out["saved"] == 1 and out["refused"][0]["text"] == "Marker"


def test_importing_twice_changes_nothing(rig: Rig) -> None:
    fb, mid, _ = imported(rig)
    assert fb.import_meeting(mid, "w1")["already_imported"] is True
    assert len(rig.services.workflow.meetings(mid)) == 1


def test_a_meeting_nobody_can_place_goes_to_review(rig: Rig) -> None:
    fb, mid, _ = sent(rig)
    capture_meeting(fb, mid, "Weekly catch up")
    out = fb.import_meeting(mid, "w1", suggested_account="Sunrise")
    meeting = rig.services.workflow.meetings(mid)[0]
    assert meeting["needs_review"] is True and meeting["match_basis"] == "suggested"
    assert rig.services.workflow.outcomes(mid) == []
    fb.link_meeting(mid, out["id"], "Sunrise")
    assert rig.services.workflow.outcomes(mid)[0].kind == "meeting_held"


def statement(text: str = "Fees are the problem", quote: str = "the fees are the main problem"):
    return {"kind": "objection", "text": text, "basis": "statement", "quote": quote}


def test_a_statement_needs_its_quote_in_the_source(rig: Rig) -> None:
    fb, mid, mtg = imported(rig)
    out = fb.add_insights(
        mid, mtg, [statement(), statement("Invented", "fees are not a problem at all")]
    )
    assert out["saved"] == 1 and out["refused"][0]["reason"] == "quote_not_in_source"
    assert fb.insights(mid)[0]["status"] == "verified"


def test_an_interpretation_waits_for_a_person(rig: Rig) -> None:
    fb, mid, mtg = imported(rig)
    fb.add_insights(
        mid, mtg, [{"kind": "urgency", "text": "Seems keen", "basis": "interpretation"}]
    )
    assert fb.insights(mid)[0]["status"] == "needs_review"


def test_a_correction_keeps_the_original(rig: Rig) -> None:
    fb, mid, mtg = imported(rig)
    fb.add_insights(
        mid, mtg, [{"kind": "urgency", "text": "Seems keen", "basis": "interpretation"}]
    )
    fb.review_insight(mid, fb.insights(mid)[0]["id"], "correct", "Keen, after exams")
    i = fb.insights(mid)[0]
    assert i["text"] == "Keen, after exams" and i["original_text"] == "Seems keen"
    assert i["status"] == "confirmed"


def test_a_rejected_insight_cannot_support_a_lesson(rig: Rig) -> None:
    fb, mid, mtg = imported(rig)
    fb.add_insights(mid, mtg, [statement()])
    iid = fb.insights(mid)[0]["id"]
    fb.review_insight(mid, iid, "reject")
    assert fb.propose_lesson(mid, "Lead with cost", "messaging", [iid])["error"] == "unsupported"


def test_a_lesson_from_one_source_cannot_be_approved(rig: Rig) -> None:
    fb, mid, mtg = imported(rig)
    fb.add_insights(mid, mtg, [statement()])
    lesson = fb.propose_lesson(mid, "Lead with cost", "messaging", [fb.insights(mid)[0]["id"]])
    assert lesson["single_source"] is True
    assert fb.decide_lesson(mid, lesson["id"], "approved")["error"] == "one_source"


def test_no_mcp_tool_can_approve_learning(rig: Rig) -> None:
    names = set(rig.tools())
    assert not names & {"decide_lesson", "decide_proposal", "conclude_experiment", "label_reply"}


def two_sources(rig: Rig) -> tuple[FeedbackService, str, dict[str, Any]]:
    """A fixture mission, so its mode teaches only fixture missions."""
    mid = ready(rig)
    wf, fb = rig.services.workflow, rig.services.feedback
    wf.build_strategy(mid)
    fb.seed_demo(mid)
    report = fb.view(mid)["report"]
    return fb, mid, next(p for p in report["proposals"] if p["dimension"] == "audience")


def approve(rig: Rig, fb: FeedbackService, mid: str, p: dict[str, Any]) -> dict[str, Any]:
    made = rig.services.workflow.add_proposal(mid, p["change"], "evidence", p["outcome_ids"])
    return fb.decide_proposal(mid, made["id"], "approved")


def test_only_a_fixture_mission_can_seed_demo_results(rig: Rig, monkeypatch: Any) -> None:
    wf, mid, _ = prepared(rig)
    fb = rig.services.feedback
    live = wf.engine.mission(mid).model_copy(update={"mode": "mixed"})
    monkeypatch.setattr(fb.engine, "mission", lambda _id: live)
    assert fb.seed_demo(mid)["error"] == "not_fixture"


def test_approval_changes_what_the_next_message_is_given(rig: Rig) -> None:
    fb, mid, p = two_sources(rig)
    out = approve(rig, fb, mid, p)
    wf = rig.services.workflow
    version = wf.strategy_versions(mid)[-1]
    assert version["body"]["guidance"] == [p["change"]] and version["version"] == out["version"]
    seen: list[str] = []
    original = wf._llm.complete  # noqa: SLF001

    def spy(req: Any) -> Any:
        seen.append(req.user)
        return original(req)

    wf._llm.complete = spy  # type: ignore[method-assign]  # noqa: SLF001
    made = {}
    for name in ("Treated one", "Treated two", "Treated three", "Treated four", "Treated five"):
        t = wf.add_target(mid, {"name": name, "audience": "parent"})
        made = wf.write_outreach(mid, t["id"])
        if made["variant"] == "treatment":
            break
    assert made["variant"] == "treatment" and made["lessons_used"]
    assert p["change"] in seen[-1] and "<approved_lessons>" in seen[-1]


def test_demo_results_compare_which_signal_led_to_meetings_too(rig: Rig) -> None:
    fb, mid, _ = two_sources(rig)
    proposals = fb.view(mid)["report"]["proposals"]
    p = next(x for x in proposals if x["dimension"] == "signal_type")
    assert p["value"] == "topic_engagement" and p["target"] == "qualification"
    assert p["rate"] > p["baseline"]


def approve_signal_lesson(rig: Rig, value: str = "recent_funding") -> str:
    wf, fb = rig.services.workflow, rig.services.feedback
    mid = ready(rig)
    wf.build_strategy(mid)
    p = wf.add_proposal(
        mid,
        f"Give {value.replace('_', ' ')} more weight in timing",
        "5 sends: 60% vs 0%",
        [],
        dimension="signal_type",
        value=value,
    )
    assert fb.decide_proposal(mid, p["id"], "approved")["ok"]
    return mid


def test_an_approved_signal_lesson_changes_the_next_missions_icp(rig: Rig) -> None:
    approve_signal_lesson(rig)
    nxt = ready(rig, "Reach more support teams next term")
    icp = rig.services.workflow.build_icp(nxt)
    assert icp["ok"] and "recent_funding" in icp["signal_types"]
    assert any("approved lesson" in a for a in icp["assumptions"])


def test_the_lesson_remembers_which_signal_it_was_about(rig: Rig) -> None:
    mid = approve_signal_lesson(rig)
    lesson = rig.services.feedback.lessons(mid)[0]
    assert lesson["dimension"] == "signal_type" and lesson["value"] == "recent_funding"


def test_a_lesson_about_something_else_adds_no_signal(rig: Rig) -> None:
    wf, fb = rig.services.workflow, rig.services.feedback
    mid = ready(rig)
    wf.build_strategy(mid)
    p = wf.add_proposal(
        mid, "Put more effort into parents", "x", [], dimension="audience", value="parent"
    )
    fb.decide_proposal(mid, p["id"], "approved")
    nxt = ready(rig, "Another goal")
    icp = wf.build_icp(nxt)
    assert "parent" not in icp["signal_types"]
    assert not any("approved lesson" in a for a in icp["assumptions"])


def test_a_holdout_target_does_not_get_the_lesson(rig: Rig) -> None:
    fb, mid, p = two_sources(rig)
    approve(rig, fb, mid, p)
    wf = rig.services.workflow
    variants = []
    for i in range(30):
        t = wf.add_target(mid, {"name": f"Target {i}", "audience": "parent"})
        made = wf.write_outreach(mid, t["id"])
        variants.append((made["variant"], made["lessons_used"]))
    assert {v for v, _ in variants} == {"holdout", "treatment"}
    assert all(not used for v, used in variants if v == "holdout")


def test_rolling_back_stops_the_lesson_reaching_new_work(rig: Rig) -> None:
    fb, mid, p = two_sources(rig)
    out = approve(rig, fb, mid, p)
    wf = rig.services.workflow
    fb.rollback(mid, out["version"] - 1)
    assert wf.strategy_versions(mid)[-1]["body"].get("guidance", []) == []
    assert fb.lessons(mid)[0]["status"] == "retired"
    assert (
        wf.lessons_for(wf._contexts.get(wf.engine.mission(mid).context_id).domain, "replay") == []
    )  # noqa: SLF001


def test_an_experiment_waits_for_results_then_a_person_decides(rig: Rig) -> None:
    fb, mid, p = two_sources(rig)
    out = approve(rig, fb, mid, p)
    exp = fb.experiments(mid)[0]
    assert exp["status"] == "running" and exp["result"]["verdict"] == "insufficient"
    assert fb.conclude_experiment(mid, exp["id"], "keep")["error"] == "insufficient"
    fb.seed_demo(mid)
    measured = fb.experiments(mid)[0]["result"]
    assert measured["after_n"] >= MIN_SAMPLE and measured["before_n"] >= MIN_SAMPLE
    assert fb.conclude_experiment(mid, exp["id"], "keep")["status"] == "kept"
    assert fb.conclude_experiment(mid, exp["id"], "keep")["error"] == "already_decided"
    assert out["experiment"] == exp["id"]


def test_rolling_back_from_an_experiment_restores_the_earlier_strategy(rig: Rig) -> None:
    fb, mid, p = two_sources(rig)
    approve(rig, fb, mid, p)
    fb.seed_demo(mid)
    exp = fb.experiments(mid)[0]
    assert fb.conclude_experiment(mid, exp["id"], "roll_back")["ok"]
    assert fb.engine.records("experiment", mid)[0]["status"] == "rolled_back"


def test_a_fixture_lesson_never_reaches_a_live_mission(rig: Rig) -> None:
    fb, mid, p = two_sources(rig)
    approve(rig, fb, mid, p)
    wf = rig.services.workflow
    domain = wf._contexts.get(wf.engine.mission(mid).context_id).domain  # noqa: SLF001
    assert wf.lessons_for(domain, "replay")
    assert wf.lessons_for(domain, "live") == [] and wf.lessons_for(domain, "mixed") == []


def test_a_new_mission_for_the_same_seller_receives_the_lesson(rig: Rig) -> None:
    fb, mid, p = two_sources(rig)
    approve(rig, fb, mid, p)
    wf = rig.services.workflow
    seen: list[str] = []
    original = wf._llm.complete  # noqa: SLF001

    def spy(req: Any) -> Any:
        seen.append(req.user)
        return original(req)

    wf._llm.complete = spy  # type: ignore[method-assign]  # noqa: SLF001
    wf._missions._llm.complete = spy  # type: ignore[method-assign]  # noqa: SLF001
    next_mission = ready(rig, "Reach more parents in the next term")
    assert next_mission != mid
    assert wf.build_strategy(next_mission)["ok"] is True
    assert wf.build_icp(next_mission)["ok"] is True
    assert sum(p["change"] in s for s in seen) >= 2
    assert wf.strategy_versions(next_mission)[-1]["body"]["lessons_used"]


@pytest.mark.parametrize(
    ("mission_mode", "name", "account_id", "expected"),
    [
        ("mixed", "Sunrise School", None, "live"),
        ("mixed", "SAMPLE school", None, "test"),
        ("mixed", "Crustdata fixture", 7, "replay"),
        ("replay", "Anything", None, "replay"),
        ("live", "Real", 7, "live"),
    ],
)
def test_an_outcome_says_what_it_is_really_about(
    mission_mode: str, name: str, account_id: int | None, expected: str
) -> None:
    from trigger_point.workflow.service import outcome_mode

    assert outcome_mode(mission_mode, {"account_name": name, "account_id": account_id}) == expected


def test_a_person_logging_a_real_send_creates_a_touch_that_counts(rig: Rig) -> None:
    wf, mid, d = prepared(rig)
    fb = rig.services.feedback
    assert fb.mark_sent(mid, d["id"], "2026-01-01")["error"] == "not_approved"
    wf.approve_outreach(mid, d["id"], d["content_hash"])
    assert fb.mark_sent(mid, d["id"], "2026-01-01")["ok"]
    touch = fb.touches(mid)[0]
    assert isinstance(touch, Touch) and touch.mode == "replay" and touch.sent_on == date(2026, 1, 1)


def test_the_view_shows_all_nine_steps(rig: Rig) -> None:
    fb, mid, p = two_sources(rig)
    approve(rig, fb, mid, p)
    view = fb.view(mid)
    assert [s["name"] for s in view["steps"]] == [
        "Capture",
        "Link",
        "Extract",
        "Check",
        "Propose",
        "Approve",
        "Version",
        "Measure",
        "Keep or roll back",
    ]
    assert view["timeline"][-1]["changes"] == [p["change"]]
    assert view["report"]["maturity_days"] == MATURITY_DAYS
