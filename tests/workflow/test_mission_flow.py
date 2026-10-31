"""The whole mission through the MCP tools, on replay fixtures, and every way it can stop."""

import json
from pathlib import Path

import httpx

from tests.workflow.conftest import (
    GOAL,
    URL,
    Rig,
    advance_to_accounts,
    advance_to_draft,
    error_body,
)
from trigger_point.mcp_server import APPROVAL_TOOLS

PROJECT = Path(__file__).resolve().parents[2]


def test_website_and_goal_create_a_real_mission(rig: Rig) -> None:
    out = rig.call("create_mission", website_url=URL, goal=GOAL)
    assert out["ok"] and out["state"] == "PROFILE_REVIEW" and out["mode"] == "replay"
    assert out["company"] and out["context_id"]
    assert rig.call("create_mission", website_url=URL, goal=GOAL)["mission_id"] == out["mission_id"]


def test_full_mission_reaches_complete_and_sends_nothing(rig: Rig) -> None:
    mid = advance_to_draft(rig)
    assert rig.call("get_mission_status", mission_id=mid)["state"] == "CAMPAIGN_DRAFTED"
    gate = rig.call("run_quality_gate", mission_id=mid)
    assert gate["ok"] and gate["passed"]
    a = rig.call("request_user_approval", mission_id=mid, gate="campaign_draft")
    assert rig.call("get_mission_status", mission_id=mid)["state"] == "USER_APPROVAL"
    done = rig.call(
        "approve_campaign_draft",
        mission_id=mid,
        approval_id=a["approval_id"],
        expected_hash=a["target_hash"],
    )
    assert done["ok"] and done["state"] == "COMPLETE" and done["sent"] is False
    status = rig.call("get_mission_status", mission_id=mid)
    assert all(t["status"] == "succeeded" for t in status["tasks"])
    types = rig.event_types(mid)
    for expected in (
        "mission.created",
        "task.queued",
        "task.started",
        "tool.started",
        "tool.completed",
        "evidence.created",
        "evidence.verified",
        "artifact.published",
        "approval.requested",
        "approval.resolved",
        "task.completed",
        "mission.completed",
    ):
        assert expected in types, expected


def test_tools_refuse_to_skip_ahead(rig: Rig) -> None:
    mid = rig.call("create_mission", website_url=URL, goal=GOAL)["mission_id"]
    out = rig.call("discover_accounts", mission_id=mid)
    assert out["ok"] is False and out["error"] == "invalid_transition"
    out = rig.call("build_icp", mission_id=mid)
    assert out["ok"] is False and out["error"] == "approval_missing"
    assert rig.provider.paths == []


def test_discovery_runs_only_after_the_plan_is_approved(rig: Rig) -> None:
    mid = rig.call("create_mission", website_url=URL, goal=GOAL)["mission_id"]
    a = rig.call("request_user_approval", mission_id=mid, gate="business_profile")
    rig.call(
        "approve_business_profile",
        mission_id=mid,
        approval_id=a["approval_id"],
        acknowledge_unsupported=True,
    )
    rig.call("build_icp", mission_id=mid)
    out = rig.call("discover_accounts", mission_id=mid)
    assert out["error"] == "approval_missing"
    assert not any("search" in p for p in rig.provider.paths)


def test_campaign_approval_needs_the_quality_gate(rig: Rig) -> None:
    mid = advance_to_draft(rig)
    out = rig.call("request_user_approval", mission_id=mid, gate="campaign_draft")
    assert out["ok"] is False and out["error"] == "approval_missing"


def test_a_changed_draft_cannot_be_approved(rig: Rig) -> None:
    mid = advance_to_draft(rig)
    rig.call("run_quality_gate", mission_id=mid)
    a = rig.call("request_user_approval", mission_id=mid, gate="campaign_draft")
    out = rig.call(
        "approve_campaign_draft",
        mission_id=mid,
        approval_id=a["approval_id"],
        expected_hash="0" * 64,
    )
    assert out["ok"] is False
    assert rig.call("get_mission_status", mission_id=mid)["state"] == "USER_APPROVAL"


def test_empty_results_wait_for_input_and_invent_nothing(rig: Rig) -> None:
    mid = advance_to_accounts(rig)

    def empty(r: httpx.Request) -> httpx.Response | None:
        if r.url.path == "/company/search":
            return httpx.Response(200, json={"companies": []}, headers={"x-credits-used": "0"})
        return None

    rig.provider.answer = empty
    out = rig.call("discover_accounts", mission_id=mid)
    assert out["ok"] and out["accounts"] == 0
    status = rig.call("get_mission_status", mission_id=mid)
    assert status["state"] == "WAITING_FOR_INPUT" and "no accounts" in status["wait_reason"]
    assert rig.call("research_account_signals", mission_id=mid)["error"] == "invalid_transition"


def test_rate_limit_needs_retry_and_retry_does_not_duplicate(rig: Rig) -> None:
    mid = advance_to_accounts(rig)

    def limited(r: httpx.Request) -> httpx.Response | None:
        if r.url.path == "/company/search":
            return httpx.Response(429, json=error_body(), headers={"retry-after": "0"})
        return None

    rig.provider.answer = limited
    out = rig.call("discover_accounts", mission_id=mid)
    assert out["ok"] is False and out["error"] == "rate_limited" and out["retryable"] is True
    assert rig.call("get_mission_status", mission_id=mid)["state"] == "NEEDS_RETRY"

    rig.provider.answer = lambda _r: None
    assert rig.call("discover_accounts", mission_id=mid)["ok"]
    status = rig.call("get_mission_status", mission_id=mid)
    assert status["state"] == "ACCOUNTS_FOUND"
    tasks = [t for t in status["tasks"] if t["kind"] == "discover_accounts"]
    assert len(tasks) == 1 and tasks[0]["attempt"] == 2
    assert rig.event_types(mid).count("task.failed") == 1


def test_auth_failure_stops_the_mission_visibly(rig: Rig) -> None:
    mid = advance_to_accounts(rig)

    def denied(r: httpx.Request) -> httpx.Response | None:
        if r.url.path == "/company/search":
            return httpx.Response(401, json=error_body("authentication_error"))
        return None

    rig.provider.answer = denied
    out = rig.call("discover_accounts", mission_id=mid)
    assert out["ok"] is False and out["error"] == "auth" and out["retryable"] is False
    assert rig.call("get_mission_status", mission_id=mid)["state"] == "FAILED"


def test_a_repeated_tool_call_does_not_repeat_the_work(rig: Rig) -> None:
    mid = advance_to_accounts(rig)
    rig.call("discover_accounts", mission_id=mid)
    calls = len(rig.provider.paths)
    before = len(rig.event_types(mid))
    again = rig.call("discover_accounts", mission_id=mid)
    assert again["ok"] and again["cached"] is True
    assert len(rig.provider.paths) == calls and len(rig.event_types(mid)) == before


def test_evidence_carries_the_whole_contract(rig: Rig) -> None:
    mid = advance_to_draft(rig)
    evidence = rig.services.workflow.engine.evidence(mid)
    assert evidence
    posting = next(e for e in evidence if e.source_url and e.event_on)
    assert posting.publisher and posting.retrieved_at and posting.excerpt
    assert posting.verification_status == "verified"
    assert all(e.verification_status != "unverified" for e in evidence)


def test_task_details_show_tools_outputs_and_evidence(rig: Rig) -> None:
    mid = advance_to_draft(rig)
    status = rig.call("get_mission_status", mission_id=mid)
    tid = next(t["id"] for t in status["tasks"] if t["kind"] == "research_signals")
    out = rig.call("get_task_details", task_id=tid)
    assert out["ok"] and out["role"] == "signal-analyst" and out["output"]
    assert any(e["type"] == "tool.completed" for e in out["events"])
    assert out["evidence_ids"]


def test_provider_calls_are_recorded_as_tool_events(rig: Rig) -> None:
    mid = advance_to_draft(rig)
    tools = [
        e.data
        for e in rig.services.workflow.engine.events(mid)
        if e.event_type == "tool.completed" and e.data.get("provider")
    ]
    assert {"/job/search", "/person/search"} <= {t["tool"] for t in tools}
    assert all(t["mode"] == "replay" for t in tools)


def test_no_tool_can_send_or_write_outward(rig: Rig) -> None:
    # These two only prepare text and record what Gmail did. Neither can reach an inbox.
    names = set(rig.tools()) - {"prepare_test_send", "record_test_send"}
    assert not {n for n in names if any(w in n for w in ("send", "post_", "publish", "linkedin"))}


def test_every_human_gate_is_ask_gated_in_project_settings() -> None:
    settings = json.loads((PROJECT / ".claude" / "settings.json").read_text())
    ask = set(settings["permissions"]["ask"])
    allow = set(settings["permissions"]["allow"])
    for tool in APPROVAL_TOOLS:
        assert f"mcp__trigger_point__{tool}" in ask, tool
        assert f"mcp__trigger_point__{tool}" not in allow, tool


def test_cancel_ends_the_mission(rig: Rig) -> None:
    mid = rig.call("create_mission", website_url=URL, goal=GOAL)["mission_id"]
    assert rig.call("cancel_mission", mission_id=mid, reason="wrong site")["state"] == "CANCELLED"
    assert rig.call("build_icp", mission_id=mid)["error"] == "invalid_transition"


def test_unsafe_url_fails_without_fetching(rig: Rig) -> None:
    out = rig.call("create_mission", website_url="http://127.0.0.1/admin", goal=GOAL)
    assert out["ok"] is False and out["error"] == "unsafe_url"


def test_every_failed_audit_says_why(rig: Rig) -> None:
    mid = advance_to_draft(rig)
    failed = [
        e
        for e in rig.services.workflow.engine.evidence(mid)
        if e.verification_status not in ("verified", "user_provided")
    ]
    assert failed
    assert all(e.verification_reasons for e in failed)


def test_status_shows_decided_approvals_too(rig: Rig) -> None:
    mid = advance_to_accounts(rig)
    status = rig.call("get_mission_status", mission_id=mid)
    assert {a["gate"]: a["status"] for a in status["approvals"]} == {
        "business_profile": "approved",
        "icp_plan": "approved",
    }


def test_fixture_mode_refuses_a_site_it_has_no_recording_of(rig: Rig) -> None:
    out = rig.call("create_mission", website_url="https://learntulip.com/", goal=GOAL)
    assert out["ok"] is False and out["error"] == "no_fixture"
    assert "supportpilot.example" in out["message"]
    assert rig.services.workflow.engine.missions() == []


def test_create_mission_reports_what_the_profile_already_holds(rig: Rig) -> None:
    out = rig.call(
        "create_mission", website_url=URL, goal=GOAL, product_description="An AI support agent"
    )
    assert out["usable"] is True
    assert "An AI support agent" in out["your_statements"]
