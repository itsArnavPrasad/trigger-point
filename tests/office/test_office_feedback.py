"""The Office side of the loop: capture from the hook, the scheduler, and a person's decisions."""

import json
from pathlib import Path
from typing import Any

import pytest

from tests.office.test_office_api import Harness
from tests.office.test_office_hook import MID, hook, run  # noqa: F401
from tests.workflow.conftest import GOAL, URL, Rig
from trigger_point.office import scheduler
from trigger_point.office.views import integration_health

READ = "mcp__claude_ai_Gmail__get_thread"


@pytest.fixture
def h(rig: Rig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    return Harness(rig, tmp_path, monkeypatch)


def post(h: Harness, path: str, body: dict[str, Any] | None = None) -> Any:
    return h.client.post(f"/api/office{path}", json=body or {}, headers=h.auth)


def mission(h: Harness) -> str:
    return str(h.rig.call("create_mission", website_url=URL, goal=GOAL)["mission_id"])


def test_the_hook_passes_the_raw_read_on_but_keeps_it_out_of_telemetry(
    hook: Any,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(hook, "call", lambda p, b=None, timeout=3.0: sent.append((p, b)))
    run(
        hook,
        monkeypatch,
        {
            "hook_event_name": "PostToolUse",
            "tool_name": READ,
            "tool_input": {"threadId": "t1", "mission_id": MID},
            "tool_response": {"messages": "private text"},
        },
    )
    assert sent[0][0] == "/hook/capture" and sent[0][1]["tool_response"]
    assert sent[1][0] == "/hook/event" and "private" not in json.dumps(sent[1][1])


def test_the_hook_does_not_capture_other_tools(
    hook: Any,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths: list[str] = []
    monkeypatch.setattr(hook, "call", lambda p, b=None, timeout=3.0: paths.append(p))
    run(
        hook,
        monkeypatch,
        {"hook_event_name": "PostToolUse", "tool_name": "mcp__claude_ai_Gmail__search_threads"},
    )
    assert "/hook/capture" not in paths


def test_a_read_nobody_allowed_is_held_for_a_person(
    hook: Any,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held: list[str] = []
    monkeypatch.setattr(hook, "permission", lambda d: held.append(d["tool_name"]))
    tool = "mcp__claude_ai_Wispr_Flow__search_meetings"
    run(hook, monkeypatch, {"hook_event_name": "PermissionRequest", "tool_name": tool})
    assert held == [tool]


def test_a_capture_reaches_the_mission_and_needs_one(h: Harness) -> None:
    mid = mission(h)
    body = {"tool": READ, "tool_input": {"threadId": "t"}, "tool_response": {"id": "t"}}
    assert post(h, "/hook/capture", {**body, "mission_id": mid}).json()["ok"] is True
    assert post(h, "/hook/capture", body).json()["error"] == "no_mission"
    assert h.rig.services.feedback._raw(mid, (READ,))  # noqa: SLF001


def test_the_mission_view_never_carries_raw_sources(h: Harness) -> None:
    mid = mission(h)
    post(
        h,
        "/hook/capture",
        {
            "tool": READ,
            "mission_id": mid,
            "tool_input": {"threadId": "t"},
            "tool_response": {"id": "t", "secret": "raw thread text"},
        },
    )
    assert "raw thread text" not in json.dumps(h.mission(mid))


def test_buttons_reach_the_director(h: Harness) -> None:
    mid = mission(h)
    for path in ("check-replies", "import-meetings", "review-learning"):
        assert post(h, f"/missions/{mid}/{path}").status_code == 202


def test_a_decision_with_a_bad_value_is_refused(h: Harness) -> None:
    mid = mission(h)
    assert post(h, f"/missions/{mid}/replies/x", {"label": "maybe"}).status_code == 422
    assert post(h, f"/missions/{mid}/experiments/x", {"decision": "ship"}).status_code == 422


def test_demo_results_show_on_the_learning_view(h: Harness) -> None:
    mid = mission(h)
    h.rig.services.workflow.build_strategy(mid)
    assert post(h, f"/missions/{mid}/demo-results").status_code == 201
    learning = h.mission(mid)["learning"]
    assert learning["demo"] is True and learning["report"]["counted"] == 10


class Runner:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, mission_id: str, text: str) -> None:
        self.sent.append((mission_id, text))


def test_the_scheduler_asks_the_director_and_sends_nothing_itself(rig: Rig) -> None:
    fb = rig.services.feedback
    mid = "wm_x"
    fb.engine.missions = lambda limit=50: [type("M", (), {"id": mid})()]  # type: ignore[method-assign]
    fb.due_sends = lambda _m: ["otr_1"]  # type: ignore[method-assign]
    runner = Runner()
    assert scheduler.tick(fb, runner) == ["otr_1"]
    assert runner.sent == [(mid, "Send a test email for outreach_id otr_1.")]


def test_wispr_shows_connected_only_when_claude_code_says_so(rig: Rig) -> None:
    def state(states: dict[str, str]) -> str:
        rows = integration_health(rig.services, states)
        return next(r["state"] for r in rows if r["id"] == "wispr")

    assert state({"claude.ai Wispr Flow": "connected"}) == "connected"
    assert state({}) == "not_connected"
