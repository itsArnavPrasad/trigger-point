"""The backend's own view of a mission: the same state Claude Code and the Office report."""

from pathlib import Path

from tests.conftest import FIXTURES, MakeClient
from tests.workflow.conftest import GOAL, URL
from trigger_point.api.app import AppDeps, build_services
from trigger_point.config import load_settings
from trigger_point.context.extractor import LlmContextExtractor
from trigger_point.llm.replay import ReplayStructuredLlm
from trigger_point.store.db import Store
from trigger_point.web.fetcher import FixtureFetcher
from trigger_point.workflow.engine import WorkflowEngine
from trigger_point.workflow.store import WorkflowStore


def test_mission_is_readable_from_the_backend(make_client: MakeClient) -> None:
    client, _ = make_client()
    services = client.app.state.services  # type: ignore[attr-defined]
    mid = services.workflow.create_mission(URL, GOAL)["mission_id"]
    listed = client.get("/api/workflow/missions").json()
    assert [m["id"] for m in listed["missions"]] == [mid]
    body = client.get(f"/api/workflow/missions/{mid}").json()
    assert body["state"] == "PROFILE_REVIEW" and body["mode"] == "replay"
    assert body["tasks"][0]["status"] == "succeeded"
    events = client.get(f"/api/workflow/missions/{mid}/events").json()["events"]
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))


def test_unknown_mission_is_a_404(make_client: MakeClient) -> None:
    client, _ = make_client()
    assert client.get("/api/workflow/missions/nope").status_code == 404
    assert client.get("/api/workflow/missions/nope/events").status_code == 404


def test_workflow_state_lives_in_the_injected_store(tmp_path: Path) -> None:
    # A caller that hands in a Store owns the data: nothing may land in the settings' database
    default_db = tmp_path / "default.db"
    settings = load_settings({"DATABASE_URL": f"sqlite:///{default_db}"})
    llm = ReplayStructuredLlm(FIXTURES / "llm")
    deps = AppDeps(
        FixtureFetcher(FIXTURES / "sites"),
        LlmContextExtractor(llm),
        Store(tmp_path / "injected.db"),
        llm,
    )
    services = build_services(settings, deps)
    mission = services.workflow.create_mission(URL, GOAL)
    assert not default_db.exists()
    fresh = WorkflowEngine(WorkflowStore(tmp_path / "injected.db"))
    assert fresh.mission(mission["mission_id"]).state == "PROFILE_REVIEW"
