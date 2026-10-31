"""The driver picks people, writes, approves and schedules, one step per pass, and never repeats."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.office.test_office_api import Harness
from tests.workflow.conftest import Rig, advance_to_draft
from trigger_point.office.autopilot import Availability
from trigger_point.office.autopilot_driver import drive, next_send_time
from trigger_point.workflow.service import audience_for


@pytest.fixture
def h(rig: Rig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    return Harness(rig, tmp_path, monkeypatch)


def run(h: Harness, mid: str) -> list[str]:
    svc = h.rig.services
    from trigger_point.office.autopilot import AutopilotService

    ap = AutopilotService(h.office, True)
    ap.save(mid, {"enabled": True})
    out: list[str] = []
    for _ in range(40):
        step = [e for e in drive(svc, h.office, ap) if e.startswith(mid)]
        if not step:
            break
        out += step
    return out


def test_audience_comes_from_what_the_account_is() -> None:
    assert audience_for(["Primary/Secondary Education"]) == "school_authority"
    assert audience_for(["Software Development"]) == "company_buyer"
    assert audience_for([]) == "company_buyer"


def test_send_time_waits_for_the_window() -> None:
    w = Availability(start="09:30", end="17:30", minutes=15)
    sat_night = datetime(2026, 10, 31, 20, 0, tzinfo=UTC)  # Sunday 01:30 IST
    t = next_send_time(w, sat_night)
    assert t.weekday() == 0 and t.hour == 9 and t.minute >= 30
    inside = datetime(2026, 11, 2, 6, 0, tzinfo=UTC)  # Monday 11:30 IST
    assert next_send_time(w, inside).hour == 11


def test_driver_goes_from_accounts_to_a_scheduled_message_and_repeats_nothing(h: Harness) -> None:
    mid = advance_to_draft(h.rig)
    effects = run(h, mid)
    kinds = [e.split(":")[1] for e in effects]
    assert {"targets", "write", "approve", "schedule"} <= set(kinds), kinds
    wf = h.rig.services.workflow
    assert wf.targets(mid), "people were chosen"
    assert all(t["source"] == "discovered" for t in wf.targets(mid))
    # A second full pass does nothing new: the work is derived from stored state.
    assert run(h, mid) == []
    log = h.office.autopilot_log(mid, 100)
    assert len({(e["kind"], e["subject"]) for e in log if e["decision"] == "allow"}) == len(
        [e for e in log if e["decision"] == "allow"]
    )


def test_a_paused_mission_is_left_alone(h: Harness) -> None:
    mid = advance_to_draft(h.rig)
    from trigger_point.office.autopilot import AutopilotService

    ap = AutopilotService(h.office, True)
    ap.save(mid, {"paused": True})
    assert drive(h.rig.services, h.office, ap) == []


def test_a_finished_mission_still_gets_its_messages_approved_and_scheduled(h: Harness) -> None:
    """The Director's own pipeline completes once its draft is approved. Outreach, replies and
    booking come after that, so Autopilot must keep going on a completed mission."""
    rig = h.rig
    mid = advance_to_draft(rig)
    assert rig.call("run_quality_gate", mission_id=mid)["passed"]
    a = rig.call("request_user_approval", mission_id=mid, gate="campaign_draft")
    done = rig.call(
        "approve_campaign_draft",
        mission_id=mid,
        approval_id=a["approval_id"],
        expected_hash=a["target_hash"],
    )
    assert done["state"] == "COMPLETE"
    kinds = [e.split(":")[1] for e in run(h, mid)]
    assert {"targets", "write", "approve", "schedule"} <= set(kinds), kinds


def test_a_failed_or_cancelled_mission_is_left_alone(h: Harness) -> None:
    mid = advance_to_draft(h.rig)
    h.rig.call("cancel_mission", mission_id=mid, reason="stopped")
    assert run(h, mid) == []


def test_an_idle_claude_code_is_told_to_continue_until_the_pipeline_moves(h: Harness) -> None:
    from datetime import timedelta

    from tests.workflow.conftest import advance_to_accounts
    from trigger_point.office.autopilot_driver import nudge
    from trigger_point.office.conversations import Conversations

    mid = advance_to_accounts(h.rig)  # ICP approved, nothing researched: Claude Code went idle
    h.office.set_run(mid, "idle", detail="success")
    convs = Conversations(h.rig.services.workflow, h.rig.services.feedback, h.office)
    sent: list[str] = []

    class R:
        def send(self, mission_id: str, text: str) -> None:
            sent.append(text)

    soon = datetime.now(UTC) + timedelta(minutes=1)
    nudge(h.office, convs, R(), mid, soon)
    assert len(sent) == 1 and "Continue with the next step" in sent[0]
    nudge(h.office, convs, R(), mid, soon + timedelta(seconds=10))  # too soon to ask again
    assert len(sent) == 1
    for i in range(1, 8):
        nudge(h.office, convs, R(), mid, soon + timedelta(minutes=4 * i))
    assert len(sent) == 4  # gives up and says so rather than looping
    assert any(
        e["decision"] == "hold" for e in h.office.autopilot_log(mid, 50) if e["kind"] == "resume"
    )
