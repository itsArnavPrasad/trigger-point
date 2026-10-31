"""The guard on anything that reaches a real inbox. It fails closed."""

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import unquote

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "office_hook.py"
GMAIL = "mcp__claude_ai_Gmail__send_message"
CAL = "mcp__claude_ai_Google_Calendar__create_event"
OK = "inbox@example.test"


@pytest.fixture
def hook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    (tmp_path / ".env").write_text(f"TRIGGER_POINT_TEST_RECIPIENTS={OK}\n")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    spec = importlib.util.spec_from_file_location("office_hook", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.call = lambda *a, **k: {}
    return module


def decide(
    hook: ModuleType, tool: str, tool_input: dict[str, Any], capsys: Any, monkeypatch: Any
) -> str:
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    hook.main()
    out = capsys.readouterr().out
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out else "pass"


@pytest.mark.parametrize(
    ("tool", "tool_input", "expected"),
    [
        (GMAIL, {"to": [OK], "subject": "x", "body": "y"}, "pass"),
        (GMAIL, {"to": [OK.upper()], "subject": "x"}, "pass"),
        (GMAIL, {"to": ["principal@school.example"], "subject": "x"}, "deny"),
        (GMAIL, {"to": [OK], "cc": ["a@b.example"]}, "deny"),
        (GMAIL, {"to": [OK], "bcc": ["a@b.example"]}, "deny"),
        (GMAIL, {"to": [OK, "a@b.example"]}, "deny"),
        (GMAIL, {"to": []}, "deny"),
        (GMAIL, {}, "deny"),
        (GMAIL, {"draftId": "d1"}, "deny"),
        (GMAIL, {"to": [OK], "replyThreadId": "t1"}, "pass"),
        (GMAIL, {"to": ["a@b.example"], "replyThreadId": "t1"}, "deny"),
        (GMAIL, {"replyThreadId": "t1"}, "deny"),
        (CAL, {"summary": "x", "attendees": [{"email": OK}]}, "pass"),
        (CAL, {"summary": "x"}, "pass"),
        (CAL, {"summary": "x", "attendees": [{"email": "a@b.example"}]}, "deny"),
        (CAL, {"summary": "x", "attendeeEmails": ["a@b.example"]}, "deny"),
    ],
)
def test_only_the_test_inbox_can_be_reached(
    hook: ModuleType,
    tool: str,
    tool_input: dict[str, Any],
    expected: str,
    capsys: Any,
    monkeypatch: Any,
) -> None:
    assert decide(hook, tool, tool_input, capsys, monkeypatch) == expected


def test_with_no_allowlist_everything_is_blocked(
    tmp_path: Path, hook: ModuleType, capsys: Any, monkeypatch: Any
) -> None:
    (tmp_path / ".env").write_text("")
    assert decide(hook, GMAIL, {"to": [OK]}, capsys, monkeypatch) == "deny"


def test_a_broken_guard_blocks(hook: ModuleType, capsys: Any, monkeypatch: Any) -> None:
    def boom() -> None:
        raise OSError("cannot read")

    monkeypatch.setattr(hook, "allowed_recipients", boom)
    assert decide(hook, GMAIL, {"to": [OK]}, capsys, monkeypatch) == "deny"


def test_a_gmail_send_is_held_for_a_person(hook: ModuleType, capsys: Any, monkeypatch: Any) -> None:
    answers = iter([{"id": "p"}, {"status": "deny", "message": "No."}])
    monkeypatch.setattr(hook, "call", lambda *a, **k: next(answers))
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "hook_event_name": "PermissionRequest",
                    "tool_name": GMAIL,
                    "tool_input": {"to": [OK]},
                }
            )
        ),
    )
    hook.main()
    assert (
        json.loads(capsys.readouterr().out)["hookSpecificOutput"]["decision"]["behavior"] == "deny"
    )


def test_live_mode_asks_the_office_and_fails_closed(
    tmp_path: Path, hook: ModuleType, capsys: Any, monkeypatch: Any
) -> None:
    (tmp_path / ".env").write_text("OUTREACH_MODE=live\n")
    prepared = "person@school.example"
    monkeypatch.setattr(hook, "call", lambda p, *a, **k: {"allowed": prepared in unquote(p)})
    assert decide(hook, GMAIL, {"to": [prepared]}, capsys, monkeypatch) == "pass"
    assert decide(hook, GMAIL, {"to": ["other@school.example"]}, capsys, monkeypatch) == "deny"
    assert (
        decide(hook, GMAIL, {"to": [prepared], "cc": ["x@y.example"]}, capsys, monkeypatch)
        == "deny"
    )
    assert decide(hook, GMAIL, {"draftId": "d"}, capsys, monkeypatch) == "deny"

    def down(*a: Any, **k: Any) -> None:
        raise OSError("office is down")

    monkeypatch.setattr(hook, "call", down)
    assert decide(hook, GMAIL, {"to": [prepared]}, capsys, monkeypatch) == "deny"
