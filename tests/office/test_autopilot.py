"""Autopilot answers only what its policy covers, logs every answer, and fails to held."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from tests.office.test_office_api import Harness
from tests.workflow.conftest import Rig
from trigger_point.config import ConfigError, load_settings
from trigger_point.office.autopilot import (
    CALENDAR_CREATE,
    GMAIL_SEND,
    AutopilotService,
    Availability,
    Context,
    Policy,
    decide,
)
from trigger_point.office.store import OfficeStore

INBOX = "demo@example.com"


def ctx(**over: Any) -> Context:
    base: dict[str, Any] = {
        "known_mission": True,
        "session_mission": "wm_1",
        "credits_spent": Decimal(0),
        "projected_credits": Decimal(5),
        "allowed_recipients": frozenset({INBOX}),
        "sends_today": 0,
        "meetings_booked": 0,
    }
    return Context(**{**base, **over})


def verdict(tool: str, tool_input: dict[str, Any] | None = None, **over: Any) -> str:
    policy = Policy(**{k: v for k, v in over.items() if k in Policy.model_fields})
    rest = {k: v for k, v in over.items() if k not in Policy.model_fields}
    return decide(policy, ctx(**rest), tool, tool_input or {}).verdict


@pytest.mark.parametrize(
    ("tool", "tool_input", "over", "expected"),
    [
        ("approve_icp_plan", {"mission_id": "wm_1"}, {}, "allow"),
        ("approve_icp_plan", {"mission_id": "wm_2"}, {}, "hold"),  # different mission
        ("approve_icp_plan", {}, {"enabled": False}, "hold"),
        ("approve_icp_plan", {}, {"paused": True}, "hold"),
        ("approve_icp_plan", {}, {"known_mission": False}, "hold"),
        ("decide_lesson", {}, {}, "hold"),  # learning stays human
        (
            "discover_accounts",
            {},
            {"credits_spent": Decimal(45), "credit_cap": 50},
            "allow",
        ),  # 45+5 == cap
        ("discover_accounts", {}, {"credits_spent": Decimal(46), "credit_cap": 50}, "hold"),
        ("discover_accounts", {}, {"credits_spent": Decimal(10**6)}, "allow"),  # no cap by default
        (GMAIL_SEND, {"to": INBOX, "body": "x"}, {}, "allow"),
        (GMAIL_SEND, {"to": ["Name <demo@example.com>"]}, {}, "allow"),
        (GMAIL_SEND, {"to": "someone@school.in"}, {}, "hold"),
        (GMAIL_SEND, {"to": INBOX, "cc": "other@x.com"}, {}, "hold"),
        (GMAIL_SEND, {"to": INBOX, "draftId": "d1"}, {}, "hold"),
        (GMAIL_SEND, {}, {}, "hold"),
        (GMAIL_SEND, {"to": 5}, {}, "hold"),
        (GMAIL_SEND, {"to": INBOX}, {"sends_today": 20}, "hold"),
        (CALENDAR_CREATE, {"attendees": [INBOX]}, {}, "hold"),  # no confirmed booking
        (
            CALENDAR_CREATE,
            {"attendees": [INBOX]},
            {"booking_attendees": frozenset({INBOX})},
            "allow",
        ),
        (
            CALENDAR_CREATE,
            {"attendees": ["x@y.com"]},
            {"booking_attendees": frozenset({INBOX})},
            "hold",
        ),
        (CALENDAR_CREATE, {}, {"booking_attendees": frozenset({INBOX})}, "hold"),
        (
            CALENDAR_CREATE,
            {"attendees": [INBOX]},
            {"booking_attendees": frozenset({INBOX}), "meetings_booked": 5},
            "hold",
        ),
    ],
)
def test_decide_table(
    tool: str, tool_input: dict[str, Any], over: dict[str, Any], expected: str
) -> None:
    assert verdict(tool, tool_input, **over) == expected


def test_availability_window_and_validation() -> None:
    a = Availability()
    monday_11 = datetime(2026, 11, 2, 5, 30, tzinfo=UTC)  # 11:00 IST
    assert a.allows(monday_11)
    assert not a.allows(datetime(2026, 11, 2, 11, 40, tzinfo=UTC))  # 17:10 IST, runs past 17:00
    assert not a.allows(datetime(2026, 11, 1, 5, 30, tzinfo=UTC))  # Sunday
    assert not a.allows(datetime(2026, 11, 2, 5, 30))  # naive time
    for bad in ({"start": "9am"}, {"timezone": "Mars/Base"}, {"start": "18:00"}, {"days": [7]}):
        with pytest.raises(ValueError):
            Availability(**bad)


def test_policy_resolution_and_bad_input_stores_nothing(tmp_path: Path) -> None:
    office = OfficeStore(tmp_path / "t.db")
    svc = AutopilotService(office, default_on=True)
    assert svc.policy_for("wm_1").enabled
    svc.save("*", {"credit_cap": 10})
    assert svc.policy_for("wm_1").credit_cap == 10  # global applies
    svc.save("wm_1", {"credit_cap": 20})
    assert svc.policy_for("wm_1").credit_cap == 20 and svc.policy_for("wm_2").credit_cap == 10
    with pytest.raises(ValueError):
        svc.save("wm_1", {"credit_cap": -1})
    assert svc.policy_for("wm_1").credit_cap == 20


def test_old_database_gains_the_column_and_keeps_rows(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as c:
        c.execute(
            "CREATE TABLE office_permissions (id TEXT PRIMARY KEY, seq INTEGER, mission_id TEXT,"
            " session_id TEXT, role TEXT, tool TEXT NOT NULL, input TEXT NOT NULL,"
            " status TEXT NOT NULL, message TEXT, at TEXT NOT NULL, decided_at TEXT)"
        )
        c.execute(
            "INSERT INTO office_permissions (id, tool, input, status, at)"
            " VALUES ('p1', 't', '{}', 'pending', 'now')"
        )
    office = OfficeStore(path)
    assert office.permission("p1")["decided_by"] is None
    assert office.decide_permission("p1", "allow", None)
    assert office.permission("p1")["decided_by"] == "human"


def test_live_mode_needs_the_send_flag_and_the_flag_needs_live() -> None:
    with pytest.raises(ConfigError):
        load_settings({"OUTREACH_MODE": "live"})
    with pytest.raises(ConfigError):
        load_settings({"ENABLE_EMAIL_SEND": "true"})
    with pytest.raises(ConfigError):
        load_settings({"OUTREACH_MODE": "maybe"})
    s = load_settings({"OUTREACH_MODE": "live", "ENABLE_EMAIL_SEND": "true"})
    assert s.outreach_mode == "live"
    assert load_settings({}).outreach_mode == "demo" and load_settings({}).autopilot_default


# --- through the hook -----------------------------------------------------------------------


@pytest.fixture
def h(rig: Rig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    return Harness(rig, tmp_path, monkeypatch)


def make_mission(h: Harness) -> str:
    return str(
        h.rig.services.workflow.engine.create_mission(
            "https://learntulip.example", "Meet schools", "replay", {}
        ).id
    )


def ask(h: Harness, mid: str, tool: str, tool_input: dict[str, Any]) -> str:
    r = h.client.post(
        "/api/office/hook/permission",
        headers=h.auth,
        json={"tool": tool, "tool_input": tool_input, "mission_id": mid},
    )
    return str(r.json()["id"])


def test_autopilot_off_leaves_prompts_for_a_human(h: Harness) -> None:
    mid = make_mission(h)
    pid = ask(h, mid, "approve_icp_plan", {"mission_id": mid})
    assert h.office.permission(pid)["status"] == "pending"


def test_autopilot_on_answers_a_gate_and_logs_it(h: Harness) -> None:
    mid = make_mission(h)
    r = h.client.put(
        f"/api/office/missions/{mid}/autopilot", headers=h.auth, json={"changes": {"enabled": True}}
    )
    assert r.status_code == 200 and r.json()["active"]
    pid = ask(h, mid, "approve_icp_plan", {"mission_id": mid})
    p = h.office.permission(pid)
    assert p["status"] == "allow" and p["decided_by"] == "autopilot"
    view = h.client.get(f"/api/office/missions/{mid}/autopilot", headers=h.auth).json()
    assert view["log"][0]["decision"] == "allow" and view["log"][0]["subject"] == pid
    # A click after the answer cannot flip it.
    late = h.client.post(
        f"/api/office/permissions/{pid}", headers=h.auth, json={"decision": "deny"}
    )
    assert late.json() == {"ok": False}


def test_a_learning_tool_is_held_with_its_reason(h: Harness) -> None:
    mid = make_mission(h)
    h.client.put(
        f"/api/office/missions/{mid}/autopilot", headers=h.auth, json={"changes": {"enabled": True}}
    )
    pid = ask(h, mid, "decide_proposal", {"mission_id": mid})
    assert h.office.permission(pid)["status"] == "pending"
    view = h.client.get(f"/api/office/missions/{mid}/autopilot", headers=h.auth).json()
    assert view["held"][pid] == "This decision is yours to make"


def test_enabling_sweeps_what_is_already_waiting(h: Harness) -> None:
    mid = make_mission(h)
    pid = ask(h, mid, "approve_business_profile", {"mission_id": mid})
    assert h.office.permission(pid)["status"] == "pending"
    h.client.put(
        f"/api/office/missions/{mid}/autopilot", headers=h.auth, json={"changes": {"enabled": True}}
    )
    assert h.office.permission(pid)["status"] == "allow"


def test_a_bad_policy_is_refused_and_pause_stops_answers(h: Harness) -> None:
    mid = make_mission(h)
    bad = h.client.put(
        f"/api/office/missions/{mid}/autopilot",
        headers=h.auth,
        json={"changes": {"credit_cap": -5}},
    )
    assert bad.status_code == 422
    h.client.put(
        f"/api/office/missions/{mid}/autopilot", headers=h.auth, json={"changes": {"enabled": True}}
    )
    h.client.post(f"/api/office/missions/{mid}/autopilot/pause", headers=h.auth)
    pid = ask(h, mid, "approve_icp_plan", {"mission_id": mid})
    assert h.office.permission(pid)["status"] == "pending"


def test_an_error_while_deciding_leaves_it_pending(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    mid = make_mission(h)
    h.client.put(
        f"/api/office/missions/{mid}/autopilot", headers=h.auth, json={"changes": {"enabled": True}}
    )

    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("x")

    monkeypatch.setattr("trigger_point.office.routes.decide", boom)
    pid = ask(h, mid, "approve_icp_plan", {"mission_id": mid})
    assert h.office.permission(pid)["status"] == "pending"


def test_the_first_prompt_carries_autopilot_only_when_it_is_on() -> None:
    from trigger_point.office.routes import NewMission, _first_prompt

    m = NewMission(website_url="https://x.example", goal="Meet schools")
    assert "Autopilot is ON" in _first_prompt(m, True)
    assert "Autopilot" not in _first_prompt(m, False)
