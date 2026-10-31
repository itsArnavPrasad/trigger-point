"""scripts/office_hook.py: telemetry sends ids only, approvals wait, and it never breaks a call."""

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "office_hook.py"
MID = "wm_0123456789abcdef"


@pytest.fixture
def hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("office_hook", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(hook: ModuleType, monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert hook.main() == 0


def test_telemetry_sends_ids_and_never_the_input_or_result(
    hook: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[dict[str, Any]] = []
    monkeypatch.setattr(hook, "call", lambda _p, b=None, timeout=3.0: sent.append(b))
    run(
        hook,
        monkeypatch,
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "mcp__trigger_point__create_mission",
            "tool_input": {"website_url": "https://private.example", "goal": "secret goal"},
            "tool_response": {"mission_id": MID, "body": "private text"},
            "agent_type": "mission-director",
        },
    )
    assert sent[0]["mission_id"] == MID and sent[0]["tool"] == "create_mission"
    assert "private" not in json.dumps(sent[0]) and "secret" not in json.dumps(sent[0])


def test_other_tools_are_ignored(hook: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[Any] = []
    monkeypatch.setattr(hook, "call", lambda *a, **k: sent.append(a))
    run(hook, monkeypatch, {"hook_event_name": "PreToolUse", "tool_name": "Read"})
    assert sent == []


def test_a_permission_waits_through_pending_then_prints_the_human_answer(
    hook: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = iter([{"status": "pending"}, {"status": "allow"}])

    def call(path: str, body: Any = None, timeout: float = 3.0) -> dict[str, Any]:
        return {"id": "perm_1"} if body is not None else next(answers)

    monkeypatch.setattr(hook, "call", call)
    run(
        hook,
        monkeypatch,
        {
            "hook_event_name": "PermissionRequest",
            "tool_name": "mcp__trigger_point__approve_icp_plan",
        },
    )
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["decision"] == {"behavior": "allow"}


def test_a_denial_carries_the_message(
    hook: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        hook,
        "call",
        lambda _p, b=None, timeout=3.0: {"id": "p"} if b else {"status": "deny", "message": "No."},
    )
    run(
        hook,
        monkeypatch,
        {
            "hook_event_name": "PermissionRequest",
            "tool_name": "mcp__trigger_point__discover_accounts",
        },
    )
    assert (
        json.loads(capsys.readouterr().out)["hookSpecificOutput"]["decision"]["behavior"] == "deny"
    )


def test_only_trigger_point_prompts_are_held(
    hook: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(hook, "call", lambda *a, **k: pytest.fail("must not call"))
    run(hook, monkeypatch, {"hook_event_name": "PermissionRequest", "tool_name": "Bash"})
    assert capsys.readouterr().out == ""


def test_office_down_prints_nothing_and_exits_zero(
    hook: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def down(*_a: Any, **_k: Any) -> None:
        raise OSError("connection refused")

    monkeypatch.setattr(hook, "call", down)
    run(
        hook,
        monkeypatch,
        {
            "hook_event_name": "PermissionRequest",
            "tool_name": "mcp__trigger_point__approve_icp_plan",
        },
    )
    assert capsys.readouterr().out == ""
