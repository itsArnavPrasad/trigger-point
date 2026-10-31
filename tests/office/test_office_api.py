"""The Office API: auth, starting missions, held approvals, chat, and honest dashboards."""

import io
import json
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.workflow.conftest import GOAL, URL, Rig, advance_to_draft
from trigger_point.office.routes import install_office, office_token
from trigger_point.office.runner import MissionRunner, director_command
from trigger_point.office.store import OfficeStore
from trigger_point.office.views import agent_status, stakeholder_role


class FakeProcess:
    """Stands in for `claude`: records stdin and plays back what a test scripts."""

    def __init__(self, lines: list[dict[str, Any]]) -> None:
        self.sent: list[str] = []
        outer = self

        class In(io.StringIO):
            def write(self, s: str) -> int:
                outer.sent.append(s)
                return len(s)

        self.stdin = In()
        self.stdout = io.StringIO("".join(json.dumps(x) + "\n" for x in lines))
        self.code: int | None = None

    def poll(self) -> int | None:
        return self.code

    def terminate(self) -> None:
        self.code = 0

    def wait(self, timeout: float | None = None) -> int:
        return 0


class Harness:
    def __init__(self, rig: Rig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TRIGGER_POINT_HOME", str(tmp_path / "home"))
        self.rig = rig
        self.script: list[dict[str, Any]] = []
        self.spawned: list[list[str]] = []
        self.procs: list[FakeProcess] = []
        self.env: dict[str, str] = {}

        def spawn(cmd: Sequence[str], env: dict[str, str]) -> FakeProcess:
            self.spawned.append(list(cmd))
            self.env = env
            p = FakeProcess(self.script)
            self.procs.append(p)
            return p

        self.office = OfficeStore(rig.services.store.path)
        self.runner = MissionRunner(self.office, spawn)
        app = FastAPI()
        install_office(app, rig.services, self.runner)
        self.token = office_token()
        self.client = TestClient(app, base_url="http://127.0.0.1")
        self.auth = {"Authorization": f"Bearer {self.token}"}

    def mission(self, mid: str) -> dict[str, Any]:
        return dict(self.client.get(f"/api/office/missions/{mid}", headers=self.auth).json())


@pytest.fixture
def h(rig: Rig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    return Harness(rig, tmp_path, monkeypatch)


NEW = {"website_url": URL, "goal": GOAL, "product_description": "An AI support agent"}


def test_every_office_route_needs_the_token(h: Harness) -> None:
    assert h.client.get("/api/office/bootstrap").status_code == 401
    bad = {"Authorization": "Bearer nope"}
    assert h.client.get("/api/office/bootstrap", headers=bad).status_code == 401
    assert h.client.get("/api/office/bootstrap", headers=h.auth).status_code == 200


def test_the_old_json_api_needs_the_token_too(h: Harness) -> None:
    assert h.client.get("/api/contexts/x").status_code == 401
    assert h.client.get("/api/contexts/x", headers=h.auth).status_code == 404


def test_a_foreign_host_or_origin_is_refused(h: Harness) -> None:
    rebind = TestClient(h.client.app, base_url="http://evil.example")
    assert rebind.get("/api/office/bootstrap", headers=h.auth).status_code == 421
    bad = {**h.auth, "Origin": "http://evil.example"}
    assert h.client.get("/api/office/bootstrap", headers=bad).status_code == 403


def test_the_token_file_is_private(h: Harness, tmp_path: Path) -> None:
    assert (tmp_path / "home" / "office-token").stat().st_mode & 0o777 == 0o600


def test_starting_a_mission_starts_the_director_with_the_request_as_data(h: Harness) -> None:
    res = h.client.post("/api/office/missions", json=NEW, headers=h.auth)
    assert res.status_code == 201
    mid = res.json()["mission_id"]
    assert h.spawned[0][:3] == ["claude", "--agent", "mission-director"]
    assert h.env["TRIGGER_POINT_MISSION_ID"] == mid
    sent = json.loads(h.procs[0].sent[0])
    assert sent["type"] == "user" and "An AI support agent" in sent["message"]["content"]
    assert "--dangerously-skip-permissions" not in " ".join(h.spawned[0])


def test_the_command_never_widens_permissions() -> None:
    cmd = " ".join(director_command(None, "m", 1.0))
    assert "bypass" not in cmd and "--allowed" not in cmd and "permission-mode" not in cmd


def test_a_message_reaches_the_same_director(h: Harness) -> None:
    mid = h.client.post("/api/office/missions", json=NEW, headers=h.auth).json()["mission_id"]
    h.client.post(f"/api/office/missions/{mid}/messages", json={"text": "Mumbai"}, headers=h.auth)
    assert len(h.spawned) == 1
    assert "Mumbai" in h.procs[0].sent[1]
    texts = [m["text"] for m in h.mission(mid)["messages"]]
    assert "Mumbai" in texts


def test_director_output_becomes_chat_cost_and_a_session_id(h: Harness) -> None:
    h.script[:] = [
        {"type": "system", "subtype": "init", "session_id": "s-1"},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Reading it."}]}},
        {
            "type": "assistant",
            "parent_tool_use_id": "t",
            "message": {"content": [{"type": "text", "text": "sub"}]},
        },
        {
            "type": "result",
            "subtype": "success",
            "session_id": "s-1",
            "total_cost_usd": 0.05,
            "uuid": "u1",
        },
    ]
    mid = h.client.post("/api/office/missions", json=NEW, headers=h.auth).json()["mission_id"]
    for t in threading.enumerate():
        if t is not threading.current_thread() and t.daemon and t.name.startswith("Thread"):
            t.join(timeout=2)
    view = h.mission(mid)
    assert [m["text"] for m in view["messages"] if m["sender"] == "director"] == ["Reading it."]
    assert view["costs"]["claude_usd"] == 0.05 and view["run"]["session_id"] == "s-1"
    assert view["costs"]["entries"][0]["basis"] == "actual"


def test_a_stopped_director_resumes_its_session(h: Harness) -> None:
    mid = h.client.post("/api/office/missions", json=NEW, headers=h.auth).json()["mission_id"]
    h.office.set_run(mid, "stopped", session_id="s-9")
    h.procs[0].code = 0
    h.client.post(f"/api/office/missions/{mid}/messages", json={"text": "go on"}, headers=h.auth)
    assert h.spawned[1][-2:] == ["--resume", "s-9"]


def test_a_held_permission_shows_and_only_a_human_answer_releases_it(h: Harness) -> None:
    mid = advance_to_draft(h.rig)
    opened = h.client.post(
        "/api/office/hook/permission",
        json={
            "tool": "mcp__trigger_point__discover_accounts",
            "tool_input": {"mission_id": mid},
            "mission_id": mid,
        },
        headers=h.auth,
    ).json()
    pending = h.mission(mid)["permissions"]
    assert pending[0]["id"] == opened["id"] and pending[0]["dashboard"] == "account-scout"
    answer = h.client.post(
        f"/api/office/permissions/{opened['id']}", json={"decision": "deny"}, headers=h.auth
    )
    assert answer.json() == {"ok": True}
    assert h.mission(mid)["permissions"] == []
    polled = h.client.get(f"/api/office/hook/permission/{opened['id']}", headers=h.auth)
    assert polled.json()["status"] == "deny"


def test_a_permission_cannot_be_answered_twice(h: Harness) -> None:
    pid = h.office.open_permission(None, None, None, "t", {})
    assert h.office.decide_permission(pid, "deny", None) is True
    assert h.office.decide_permission(pid, "allow", None) is False
    assert h.office.permission(pid)["status"] == "deny"  # type: ignore[index]


def test_a_decision_must_be_allow_or_deny(h: Harness) -> None:
    pid = h.office.open_permission(None, None, None, "t", {})
    res = h.client.post(
        f"/api/office/permissions/{pid}", json={"decision": "maybe"}, headers=h.auth
    )
    assert res.status_code == 422


def test_hook_activity_joins_the_mission_by_session(h: Harness) -> None:
    mid = advance_to_draft(h.rig)
    h.client.post(
        "/api/office/hook/event",
        json={
            "kind": "tool_started",
            "summary": "a",
            "mission_id": mid,
            "session_id": "s",
            "role": "account-scout",
        },
        headers=h.auth,
    )
    h.client.post(
        "/api/office/hook/event",
        json={"kind": "tool_finished", "summary": "b", "session_id": "s", "role": "account-scout"},
        headers=h.auth,
    )
    assert [a["summary"] for a in h.office.activity(mid)] == ["a", "b"]


def test_dashboards_show_real_records(h: Harness) -> None:
    mid = advance_to_draft(h.rig)
    v = h.mission(mid)
    assert v["icp"][0]["criteria"] and v["profile"]["company"]
    assert v["funnel"]["found"] >= v["funnel"]["kept"] >= v["funnel"]["qualified"] >= 1
    best = next(a for a in v["accounts"] if a["name"] == "Ledgerloop")
    known = [s for s in best["stakeholders"] if s["known"]]
    assert known and known[0]["role"] and known[0]["purpose"] and known[0]["ask"]
    assert all(e["signal_status"] in ("VERIFIED", "STALE", "NEEDS_REVIEW") for e in v["evidence"])
    assert v["draft"]["sending"] == "disabled" and v["case"]
    assert {a["role"] for a in v["agents"]} >= {"icp-strategist", "quality-gatekeeper"}


def test_integrations_never_claim_a_connection_that_does_not_exist(h: Harness) -> None:
    health = h.client.get("/api/office/bootstrap", headers=h.auth).json()["health"]
    states = {x["id"]: x["state"] for x in health}
    assert states["wispr"] == "not_connected" and states["crm"] == "not_connected"
    assert states["email"] == "disabled" and states["crustdata"] == "no_key"


def test_crustdata_shows_live_once_a_live_discovery_run_completes(h: Harness) -> None:
    from datetime import UTC, datetime

    from trigger_point.mission.service import DiscoveryRun

    before = h.client.get("/api/office/bootstrap", headers=h.auth).json()["health"]
    assert next(x for x in before if x["id"] == "crustdata")["state"] == "no_key"
    h.rig.services.store.save_discovery(
        DiscoveryRun(
            id="disc_live_1",
            mission_id="wm_x",
            mode="live",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            outcome="completed",
        )
    )
    after = h.client.get("/api/office/bootstrap", headers=h.auth).json()["health"]
    crust = next(x for x in after if x["id"] == "crustdata")
    assert crust["state"] == "live" and crust["last_success"]


def test_cancel_stops_the_director_and_denies_open_prompts(h: Harness) -> None:
    mid = h.client.post("/api/office/missions", json=NEW, headers=h.auth).json()["mission_id"]
    pid = h.office.open_permission(mid, None, None, "t", {})
    out = h.client.post(f"/api/office/missions/{mid}/cancel", headers=h.auth).json()
    assert out["state"] == "CANCELLED"
    assert h.office.permission(pid)["status"] == "deny"  # type: ignore[index]
    assert h.procs[0].code == 0


@pytest.mark.parametrize(
    ("title", "role"),
    [
        ("Chief Customer Officer", "Economic buyer"),
        ("VP Customer Experience", "Executive sponsor"),
        ("Head of Support", "Functional owner"),
        ("Support Operations Manager", "Champion"),
        ("Support Specialist", "End user or practitioner"),
    ],
)
def test_stakeholder_role_from_title(title: str, role: str) -> None:
    assert stakeholder_role(title) == role


def test_a_director_that_finished_its_turn_is_waiting_for_input() -> None:
    assert (
        agent_status("mission-director", [], False, False, director_waiting=True) == "waiting_input"
    )


def test_agent_status_comes_only_from_real_state() -> None:
    t = [{"role": "account-scout", "status": "queued"}]
    assert agent_status("account-scout", t, False, False) == "idle"
    assert agent_status("account-scout", t, True, False) == "waiting_approval"
    assert (
        agent_status(
            "account-scout", [{"role": "account-scout", "status": "running"}], False, False
        )
        == "running"
    )
    assert (
        agent_status("account-scout", [{"role": "account-scout", "status": "failed"}], False, False)
        == "failed"
    )


def test_the_stream_says_it_is_alive_more_often_than_the_browser_gives_up() -> None:
    routes = Path("src/trigger_point/office/routes.py").read_text()
    client = Path("office/src/api.ts").read_text()
    assert "> 10:" in routes and "SILENCE_MS = 25_000" in client
