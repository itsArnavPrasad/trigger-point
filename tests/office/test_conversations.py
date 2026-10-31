"""A reply becomes a booked meeting or a recorded no, and only when the person's own words say so."""

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from tests.office.test_autopilot import ask
from tests.office.test_office_api import Harness
from tests.workflow.conftest import Rig, advance_to_draft
from trigger_point.llm.base import LlmError, LlmResponse
from trigger_point.office.autopilot import CALENDAR_CREATE, AutopilotService, Policy
from trigger_point.office.autopilot_driver import drive
from trigger_point.office.conversations import Conversations
from trigger_point.workflow.conversation import ReplyWire, suggest_slots

INBOX = "demo@example.com"


class FakeLlm:
    def __init__(self) -> None:
        self.wire: ReplyWire | LlmError = ReplyWire(intent="ambiguous")

    @property
    def mode(self) -> str:
        return "replay"

    def complete(self, req: Any) -> Any:
        if isinstance(self.wire, LlmError):
            raise self.wire
        return LlmResponse(output=self.wire, usage=None, mode="replay")


@pytest.fixture
def h(rig: Rig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    return Harness(rig, tmp_path, monkeypatch)


class World:
    def __init__(self, h: Harness) -> None:
        self.h = h
        self.wf = h.rig.services.workflow
        self.fb = h.rig.services.feedback
        self.wf.test_recipients = (INBOX,)
        self.llm = FakeLlm()
        self.ap = AutopilotService(h.office, True)
        self.convs = Conversations(self.wf, self.fb, h.office)
        self.mid = advance_to_draft(h.rig)
        self.ap.save(self.mid, {"enabled": True})
        for _ in range(40):
            if not [
                e for e in drive(h.rig.services, h.office, self.ap, self.convs) if self.mid in e
            ]:
                break
        self.wf._llm = self.llm  # type: ignore[assignment]  # only replies need the fake
        self.convs.record_busy(self.mid, [])  # an empty calendar, read just now
        self.outreach = self.wf.outreach(self.mid)[0]
        self.wf.record_test_send(self.mid, self.outreach["id"], INBOX, "msg0", "thread0")
        self.policy: Policy = self.ap.policy_for(self.mid)

    def reply(self, body: str, mid: str = "m1") -> str | None:
        o = self.wf.outreach(self.mid)[0]
        self.fb._add_reply(self.mid, o, mid, INBOX, body, date.today())
        return self.convs.process(self.mid, self.policy)

    @property
    def conv(self) -> dict[str, Any]:
        c = self.convs.get(self.mid, self.outreach["target_id"])
        assert c is not None
        return c

    def slot(self) -> str:
        a = self.policy.availability
        return suggest_slots(a.days, a.start, a.end, a.timezone, a.minutes, datetime.now(UTC))[0][
            "start"
        ]


def test_a_yes_with_a_time_in_the_window_is_booked_and_shown(h: Harness) -> None:
    w = World(h)
    start = w.slot()
    w.llm.wire = ReplyWire(
        intent="yes_with_time", quote="Yes, that works for us", chosen_start=start
    )
    w.reply("Yes, that works for us. See you then.")
    assert w.conv["state"] == "booking" and w.conv["token"].startswith("TP-")
    tid = w.outreach["target_id"]
    booking = w.convs.get_booking(w.mid, tid, 30, "Asia/Kolkata")
    assert booking["ok"] and booking["attendee"] == INBOX and booking["title"].startswith("TP-")
    # The calendar call is answered by policy only because it carries that code and attendee.
    pid = ask(
        h, w.mid, CALENDAR_CREATE, {"summary": booking["title"], "attendees": [{"email": INBOX}]}
    )
    assert h.office.permission(pid)["decided_by"] == "autopilot"
    other = ask(
        h,
        w.mid,
        CALENDAR_CREATE,
        {"summary": booking["title"], "attendees": [{"email": "x@y.com"}]},
    )
    assert h.office.permission(other)["status"] == "pending"
    nocode = ask(h, w.mid, CALENDAR_CREATE, {"summary": "Hello", "attendees": [{"email": INBOX}]})
    assert h.office.permission(nocode)["status"] == "pending"
    done = w.convs.record_booked_meeting(
        w.mid, tid, booking["token"], "evt1", "https://meet.google.com/x", 30, "Asia/Kolkata"
    )
    assert done["ok"] and w.conv["state"] == "booked"
    meeting = next(m for m in w.wf.meetings(w.mid) if m["source"] == "autopilot")
    assert meeting["prep"] and meeting["link"] and meeting["demo"] is True
    assert [o.kind for o in w.wf.outcomes(w.mid)].count("meeting_booked") == 1
    again = w.convs.record_booked_meeting(
        w.mid, tid, booking["token"], "evt1", "", 30, "Asia/Kolkata"
    )
    assert again["ok"] is False  # a code books once


def test_a_no_records_the_reason_in_their_own_words(h: Harness) -> None:
    w = World(h)
    w.llm.wire = ReplyWire(intent="no", quote="not interested", reason="we already have a tutor")
    w.reply("Thanks, but we are not interested. We already have a tutor.")
    assert w.conv["state"] == "declined"
    assert w.conv["decline_reason"] == "we already have a tutor"
    assert w.wf.is_suppressed(w.mid, w.outreach["target_id"])
    assert w.convs.prepare_reply(w.mid, w.outreach["target_id"])["ok"] is False


def test_words_the_person_never_wrote_are_not_believed(h: Harness) -> None:
    w = World(h)
    w.llm.wire = ReplyWire(intent="no", quote="please remove me forever")
    w.reply("Can you tell me more about pricing?")
    assert w.conv["state"] == "needs_you" and w.conv["decline_reason"] is None


def test_a_model_failure_goes_to_the_founder(h: Harness) -> None:
    w = World(h)
    w.llm.wire = LlmError("timeout", "slow")
    w.reply("Sounds interesting.")
    assert w.conv["state"] == "needs_you"


def test_a_yes_without_a_time_gets_times_offered_inside_the_window(h: Harness) -> None:
    w = World(h)
    w.llm.wire = ReplyWire(intent="yes", quote="happy to talk")
    w.reply("Happy to talk, send me options.")
    assert w.conv["state"] == "replying" and len(w.conv["slots"]) == 3
    a = w.policy.availability
    assert all(a.allows(datetime.fromisoformat(s["start"])) for s in w.conv["slots"])
    prepared = w.convs.prepare_reply(w.mid, w.outreach["target_id"])
    assert prepared["ok"] and prepared["to"] == [INBOX] and prepared["replyThreadId"] == "thread0"
    assert w.convs.record_reply_sent(w.mid, w.outreach["target_id"], "msg1")["ok"]
    assert w.conv["state"] == "awaiting_reply"
    assert w.convs.prepare_reply(w.mid, w.outreach["target_id"])["ok"] is False  # sent once


def test_a_time_outside_the_window_is_countered_with_times_that_fit(h: Harness) -> None:
    w = World(h)
    sunday = "2026-11-08T11:00:00+05:30"
    w.llm.wire = ReplyWire(intent="counter_time", quote="Sunday at 11", chosen_start=sunday)
    w.reply("Could we do Sunday at 11?")
    assert w.conv["state"] == "replying" and w.conv["outbox"]["kind"] == "offer"


def test_the_same_reply_is_read_once(h: Harness) -> None:
    w = World(h)
    w.llm.wire = ReplyWire(intent="yes", quote="happy to talk")
    w.reply("Happy to talk.")
    turns = len(w.conv["turns"])
    assert w.convs.process(w.mid, w.policy) is None
    assert len(w.conv["turns"]) == turns


def test_silence_closes_the_conversation(h: Harness) -> None:
    w = World(h)
    w.llm.wire = ReplyWire(intent="yes", quote="happy to talk")
    w.reply("Happy to talk.")
    w.convs.record_reply_sent(w.mid, w.outreach["target_id"], "msg1")
    later = datetime.now(UTC).replace(year=datetime.now(UTC).year + 1)
    w.fb.now = lambda: later
    assert w.convs.process(w.mid, w.policy) is not None
    assert w.conv["state"] == "stalled"


def test_an_opt_out_stops_everything_without_asking_the_model(h: Harness) -> None:
    w = World(h)
    w.reply("Please unsubscribe me from your list.")
    assert w.conv["state"] == "declined"


def test_a_reply_waits_until_the_calendar_has_been_read(h: Harness) -> None:
    w = World(h)
    later = datetime.now(UTC).replace(year=datetime.now(UTC).year + 1)
    w.fb.now = lambda: later  # what we know about the calendar is now stale
    w.llm.wire = ReplyWire(intent="yes", quote="happy to talk")
    assert w.reply("Happy to talk.") is None
    assert w.convs.needs_calendar(w.mid)
    w.convs.record_busy(w.mid, [])
    assert w.convs.process(w.mid, w.policy) is not None


def test_a_time_that_clashes_with_my_calendar_is_not_booked(h: Harness) -> None:
    from datetime import timedelta

    w = World(h)
    start = datetime.fromisoformat(w.slot())
    w.convs.record_busy(
        w.mid,
        [
            {
                "start": (start - timedelta(minutes=10)).isoformat(),
                "end": (start + timedelta(minutes=10)).isoformat(),
            }
        ],
    )
    w.llm.wire = ReplyWire(
        intent="yes_with_time", quote="Yes, that works", chosen_start=start.isoformat()
    )
    w.reply("Yes, that works for us.")
    assert w.conv["state"] == "replying"  # offered other times instead
    assert all(
        abs(datetime.fromisoformat(s["start"]) - start) >= timedelta(minutes=20)
        for s in w.conv["slots"]
    )


def test_suggested_times_skip_busy_ones_and_bad_busy_entries_are_dropped(h: Harness) -> None:
    from datetime import timedelta

    w = World(h)
    a = w.policy.availability
    now = datetime.now(UTC)
    first = datetime.fromisoformat(
        suggest_slots(a.days, a.start, a.end, a.timezone, a.minutes, now)[0]["start"]
    )
    busy = [(first, first + timedelta(hours=1))]
    again = suggest_slots(a.days, a.start, a.end, a.timezone, a.minutes, now, busy=busy)
    assert all(datetime.fromisoformat(s["start"]) != first for s in again) and len(again) == 3
    out = w.convs.record_busy(
        w.mid,
        [
            {"start": "soon", "end": "later"},
            {"start": "2026-11-02T10:00:00", "end": "2026-11-02T11:00:00"},
            {},
        ],
    )
    assert out["busy"] == 0 and out["skipped"] == 3  # no offset, no entry


def test_reading_the_calendar_needs_no_click_but_writing_still_does() -> None:
    from tests.office.test_autopilot import ctx
    from trigger_point.office.autopilot import decide

    read = "mcp__claude_ai_Google_Calendar__list_events"
    assert decide(Policy(), ctx(), read, {}).allowed
    assert not decide(Policy(), ctx(), "mcp__claude_ai_Google_Calendar__delete_event", {}).allowed
