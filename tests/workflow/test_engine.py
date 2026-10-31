"""The mission state machine: order, idempotency, retries, approvals and the event log."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trigger_point.workflow.engine import (
    ApprovalMissing,
    InvalidTransition,
    MissionNotFound,
    TaskBusy,
    WorkflowEngine,
)
from trigger_point.workflow.models import FLOW, TASK_PLAN, WorkflowEvent
from trigger_point.workflow.store import WorkflowStore

URL, GOAL = "https://seller.example", "Book meetings"
MODES = {"web": "replay", "llm": "replay", "crustdata": "replay"}


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 31, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


def engine(tmp_path: Path) -> WorkflowEngine:
    return WorkflowEngine(WorkflowStore(tmp_path / "wf.db"), clock=Clock())


def types(e: WorkflowEngine, mission_id: str) -> list[str]:
    return [ev.event_type for ev in e.events(mission_id)]


def to_icp(e: WorkflowEngine) -> str:
    """A mission that has passed intake and profile approval."""
    m = e.create_mission(URL, GOAL, "replay", MODES)
    t = e.begin_task(m.id, "profile_intake").task
    e.complete_task(t.id, {"company": "Seller"})
    a = e.request_approval(m.id, "business_profile", "hash-1", "Review the profile")
    e.resolve_approval(a.id, "approved", "local-user", "hash-1")
    return m.id


def test_flow_is_the_documented_state_order() -> None:
    assert FLOW == (
        "RECEIVED",
        "PROFILE_REVIEW",
        "ICP_READY",
        "ACCOUNTS_FOUND",
        "SIGNALS_RESEARCHED",
        "PEOPLE_MAPPED",
        "EVIDENCE_VERIFIED",
        "CAMPAIGN_DRAFTED",
        "USER_APPROVAL",
        "COMPLETE",
    )


def test_create_mission_queues_the_whole_plan_in_order(tmp_path: Path) -> None:
    e = engine(tmp_path)
    m = e.create_mission(URL, GOAL, "replay", MODES)
    assert m.state == "RECEIVED"
    assert [t.kind for t in e.tasks(m.id)] == [p.kind for p in TASK_PLAN]
    assert all(t.status == "queued" for t in e.tasks(m.id))
    assert types(e, m.id) == ["mission.created"] + ["task.queued"] * len(TASK_PLAN)


def test_same_request_returns_the_open_mission_without_new_events(tmp_path: Path) -> None:
    e = engine(tmp_path)
    m = e.create_mission(URL, GOAL, "replay", MODES)
    before = len(e.events(m.id))
    assert e.create_mission(URL, GOAL, "replay", MODES).id == m.id
    assert len(e.events(m.id)) == before


def test_a_state_cannot_be_skipped(tmp_path: Path) -> None:
    e = engine(tmp_path)
    m = e.create_mission(URL, GOAL, "replay", MODES)
    with pytest.raises(InvalidTransition):
        e.begin_task(m.id, "discover_accounts")
    with pytest.raises(MissionNotFound):
        e.begin_task("nope", "discover_accounts")


def test_completing_a_task_advances_the_mission(tmp_path: Path) -> None:
    e = engine(tmp_path)
    m = e.create_mission(URL, GOAL, "replay", MODES)
    t = e.begin_task(m.id, "profile_intake").task
    assert t.status == "running" and t.attempt == 1
    e.complete_task(t.id, {"company": "Seller"}, ["ctx_1"])
    assert e.mission(m.id).state == "PROFILE_REVIEW"
    assert e.task(t.id).output == {"company": "Seller"}
    assert e.task(t.id).artifact_ids == ["ctx_1"]


def test_a_finished_task_is_returned_not_rerun(tmp_path: Path) -> None:
    e = engine(tmp_path)
    m = e.create_mission(URL, GOAL, "replay", MODES)
    t = e.begin_task(m.id, "profile_intake").task
    e.complete_task(t.id, {"company": "Seller"})
    before = len(e.events(m.id))
    again = e.begin_task(m.id, "profile_intake")
    assert again.cached and again.task.attempt == 1
    assert len(e.events(m.id)) == before


def test_a_running_task_cannot_be_claimed_twice(tmp_path: Path) -> None:
    e = engine(tmp_path)
    m = e.create_mission(URL, GOAL, "replay", MODES)
    e.begin_task(m.id, "profile_intake")
    with pytest.raises(TaskBusy):
        e.begin_task(m.id, "profile_intake")


def test_a_crashed_task_can_be_taken_over_after_its_lease(tmp_path: Path) -> None:
    clock = Clock()
    e = WorkflowEngine(WorkflowStore(tmp_path / "wf.db"), clock=clock)
    m = e.create_mission(URL, GOAL, "replay", MODES)
    e.begin_task(m.id, "profile_intake")
    clock.now += timedelta(hours=1)
    assert e.begin_task(m.id, "profile_intake").task.attempt == 2


def test_gated_task_needs_its_approval(tmp_path: Path) -> None:
    e = engine(tmp_path)
    m = e.create_mission(URL, GOAL, "replay", MODES)
    t = e.begin_task(m.id, "profile_intake").task
    e.complete_task(t.id, {})
    with pytest.raises(ApprovalMissing):
        e.begin_task(m.id, "build_icp")
    a = e.request_approval(m.id, "business_profile", "hash-1", "Review")
    with pytest.raises(ApprovalMissing):  # pending is not approved
        e.begin_task(m.id, "build_icp")
    e.resolve_approval(a.id, "approved", "local-user", "hash-1")
    assert e.begin_task(m.id, "build_icp").task.status == "running"


def test_approval_is_bound_to_the_exact_content(tmp_path: Path) -> None:
    e = engine(tmp_path)
    m = e.create_mission(URL, GOAL, "replay", MODES)
    t = e.begin_task(m.id, "profile_intake").task
    e.complete_task(t.id, {})
    a = e.request_approval(m.id, "business_profile", "hash-1", "Review")
    with pytest.raises(ApprovalMissing):
        e.resolve_approval(a.id, "approved", "local-user", "hash-2")
    assert e.approval(a.id).status == "pending"


def test_requesting_the_same_approval_twice_is_one_approval(tmp_path: Path) -> None:
    e = engine(tmp_path)
    m = e.create_mission(URL, GOAL, "replay", MODES)
    t = e.begin_task(m.id, "profile_intake").task
    e.complete_task(t.id, {})
    first = e.request_approval(m.id, "business_profile", "hash-1", "Review")
    second = e.request_approval(m.id, "business_profile", "hash-1", "Review")
    assert first.id == second.id
    assert types(e, m.id).count("approval.requested") == 1


def test_rejected_approval_waits_for_input_until_new_content(tmp_path: Path) -> None:
    e = engine(tmp_path)
    m = e.create_mission(URL, GOAL, "replay", MODES)
    t = e.begin_task(m.id, "profile_intake").task
    e.complete_task(t.id, {})
    a = e.request_approval(m.id, "business_profile", "hash-1", "Review")
    e.resolve_approval(a.id, "rejected", "local-user", "hash-1", reason="wrong ICP")
    assert e.mission(m.id).state == "WAITING_FOR_INPUT"
    e.request_approval(m.id, "business_profile", "hash-2", "Review v2")
    assert e.mission(m.id).state == "PROFILE_REVIEW"


def test_retryable_failure_needs_retry_then_reruns_same_task(tmp_path: Path) -> None:
    e = engine(tmp_path)
    mid = to_icp(e)
    t = e.begin_task(mid, "build_icp").task
    e.fail_task(t.id, "rate_limited", "slow down", retryable=True)
    assert e.mission(mid).state == "NEEDS_RETRY"
    assert e.task(t.id).status == "failed"
    again = e.begin_task(mid, "build_icp").task
    assert again.id == t.id and again.attempt == 2
    assert e.mission(mid).state == "PROFILE_REVIEW"
    assert len([x for x in e.tasks(mid) if x.kind == "build_icp"]) == 1
    e.complete_task(again.id, {})
    assert e.mission(mid).state == "ICP_READY"


def test_failure_events_for_each_attempt_are_distinct(tmp_path: Path) -> None:
    e = engine(tmp_path)
    mid = to_icp(e)
    t = e.begin_task(mid, "build_icp").task
    e.fail_task(t.id, "server", "boom", retryable=True)
    t = e.begin_task(mid, "build_icp").task
    e.fail_task(t.id, "server", "boom", retryable=True)
    assert types(e, mid).count("task.failed") == 2


def test_retries_are_capped(tmp_path: Path) -> None:
    e = engine(tmp_path)
    mid = to_icp(e)
    for _ in range(3):
        t = e.begin_task(mid, "build_icp").task
        e.fail_task(t.id, "server", "boom", retryable=True)
    assert e.mission(mid).state == "FAILED"
    with pytest.raises(InvalidTransition):
        e.begin_task(mid, "build_icp")


def test_non_retryable_failure_ends_the_mission(tmp_path: Path) -> None:
    e = engine(tmp_path)
    mid = to_icp(e)
    t = e.begin_task(mid, "build_icp").task
    e.fail_task(t.id, "auth", "bad key", retryable=False)
    assert e.mission(mid).state == "FAILED"
    assert e.mission(mid).failure == "auth: bad key"


def test_cancel_stops_queued_tasks_and_blocks_work(tmp_path: Path) -> None:
    e = engine(tmp_path)
    m = e.create_mission(URL, GOAL, "replay", MODES)
    e.cancel_mission(m.id, "changed my mind")
    assert e.mission(m.id).state == "CANCELLED"
    assert {t.status for t in e.tasks(m.id)} == {"cancelled"}
    with pytest.raises(InvalidTransition):
        e.begin_task(m.id, "profile_intake")


def test_a_cancelled_mission_can_be_requested_again(tmp_path: Path) -> None:
    e = engine(tmp_path)
    m = e.create_mission(URL, GOAL, "replay", MODES)
    e.cancel_mission(m.id, "no")
    assert e.create_mission(URL, GOAL, "replay", MODES).id != m.id


def test_events_are_gapless_and_carry_the_schema(tmp_path: Path) -> None:
    e = engine(tmp_path)
    mid = to_icp(e)
    events = e.events(mid)
    assert [ev.seq for ev in events] == list(range(1, len(events) + 1))
    assert len({ev.event_id for ev in events}) == len(events)
    started = next(ev for ev in events if ev.event_type == "task.started")
    assert started.mission_id == mid and started.task_id and started.agent_id
    assert started.role == "mission-director" and started.status == "running"
    assert started.summary and started.occurred_at


def test_state_survives_a_new_engine_on_the_same_database(tmp_path: Path) -> None:
    e = engine(tmp_path)
    mid = to_icp(e)
    fresh = engine(tmp_path)
    assert fresh.mission(mid).state == "PROFILE_REVIEW"
    assert [t.status for t in fresh.tasks(mid)][0] == "succeeded"


def test_summaries_never_carry_contact_data_or_keys(tmp_path: Path) -> None:
    e = engine(tmp_path)
    m = e.create_mission(URL, GOAL, "replay", MODES)
    t = e.begin_task(m.id, "profile_intake").task
    e.fail_task(t.id, "x", "call jane@acme.example with sk-abcdef1234567890 now", retryable=True)
    failed = next(ev for ev in e.events(m.id) if ev.event_type == "task.failed")
    assert "jane@" not in failed.summary and "sk-abc" not in failed.summary


def test_undelivered_events_flush_in_order_and_only_once(tmp_path: Path) -> None:
    sent: list[int] = []

    class Sink:
        ok = False

        def deliver(self, events: list[object]) -> bool:
            if self.ok:
                sent.extend(ev.seq for ev in events)  # type: ignore[attr-defined]
            return self.ok

    sink = Sink()
    e = WorkflowEngine(WorkflowStore(tmp_path / "wf.db"), sink=sink, clock=Clock())
    m = e.create_mission(URL, GOAL, "replay", MODES)  # sink down: nothing lost, nothing raised
    sink.ok = True
    e.flush()
    e.flush()
    assert sent == list(range(1, len(e.events(m.id)) + 1))


def test_events_stored_with_the_old_schema_still_load() -> None:
    old = {
        "event_id": "evt_1",
        "seq": 1,
        "type": "mission.started",
        "occurred_at": "2026-10-31T00:00:00Z",
        "mission_id": "wm_1",
        "summary": "x",
    }
    event = WorkflowEvent.model_validate(old)
    assert event.event_type == "mission.created"
    assert event.recorded_at == event.occurred_at
