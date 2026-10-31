#!/usr/bin/env python3
"""Claude Code hook -> Trigger Point Office. Telemetry, plus holding permission prompts for the Office.

Stdlib only, and it never fails the tool call: if the Office is down it exits 0 and Claude Code's
own prompt stays in charge. Only ids and a short summary leave this script, never tool results.
On PermissionRequest it waits for the human's answer in the Office and prints that answer."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = (
    os.environ.get("TRIGGER_POINT_OFFICE_URL", "http://127.0.0.1:8000").rstrip("/") + "/api/office"
)
HOME = Path(os.environ.get("TRIGGER_POINT_HOME") or Path.home() / ".trigger-point")
MISSION = re.compile(r"wm_[0-9a-f]{16}")
GMAIL_SEND = "mcp__claude_ai_Gmail__send_message"
CALENDAR_CREATE = "mcp__claude_ai_Google_Calendar__create_event"
GUARDED = (GMAIL_SEND, CALENDAR_CREATE)
MAX_WAIT_SECONDS = 3500  # under the 3600 s hook timeout in .claude/settings.json


def call(path, body=None, timeout=3.0):
    token = (HOME / "office-token").read_text().strip()
    req = urllib.request.Request(  # noqa: S310 - loopback URL from configuration
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:  # noqa: S310
        return json.load(res)


def allowed_recipients():
    """The test inbox from the project's .env. Absent means nothing can be reached."""
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or ".")
    for line in (root / ".env").read_text().splitlines():
        if line.strip().startswith("TRIGGER_POINT_TEST_RECIPIENTS="):
            value = line.split("=", 1)[1]
            return {r.strip().strip("\"'").casefold() for r in value.split(",") if r.strip()}
    return set()


def guard_problem(tool, inp):
    """Why this call may not leave the machine, or None. Anything unclear is a refusal."""
    allowed = allowed_recipients()
    if not allowed:
        return "TRIGGER_POINT_TEST_RECIPIENTS is not set, so nothing may be sent."
    if tool == GMAIL_SEND:
        if inp.get("draftId") or inp.get("replyThreadId") or inp.get("replyToMessageId"):
            return "Test sends must be new messages, with recipients stated."
        to = list(inp.get("to") or [])
        if not to:
            return "No recipient stated."
        everyone = to + list(inp.get("cc") or []) + list(inp.get("bcc") or [])
    else:
        everyone = [a.get("email", "") for a in inp.get("attendees") or []]
        everyone += list(inp.get("attendeeEmails") or [])
    outside = [r for r in everyone if str(r).strip().casefold() not in allowed]
    return f"Blocked: {len(outside)} recipient(s) outside the test inbox." if outside else None


def guard(tool, inp):
    try:
        problem = guard_problem(tool, inp if isinstance(inp, dict) else {})
    except Exception:  # noqa: BLE001 - a broken guard must block, never pass
        problem = "The send guard could not run, so this is blocked."
    if problem:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": problem,
                    }
                }
            )
        )
    return problem


def mission_of(d):
    inp = d.get("tool_input") if isinstance(d.get("tool_input"), dict) else {}
    found = str(inp.get("mission_id") or inp.get("task_id") or "").split(".")[0]
    if not MISSION.fullmatch(found):
        m = (
            MISSION.search(json.dumps(d.get("tool_response"), default=str))
            if "tool_response" in d
            else None
        )
        found = m.group(0) if m else os.environ.get("TRIGGER_POINT_MISSION_ID", "")
    return found if MISSION.fullmatch(found) else None


def short_tool(name):
    return str(name or "").removeprefix("mcp__trigger_point__")


def permission(d):
    opened = call(
        "/hook/permission",
        {
            "tool": str(d.get("tool_name")),
            "tool_input": d.get("tool_input") if isinstance(d.get("tool_input"), dict) else {},
            "mission_id": mission_of(d),
            "session_id": d.get("session_id"),
            "role": d.get("agent_type"),
        },
    )
    end = time.monotonic() + MAX_WAIT_SECONDS
    while time.monotonic() < end:
        answer = call(f"/hook/permission/{opened['id']}", timeout=35.0)
        if answer["status"] == "allow":
            decision = {"behavior": "allow"}
        elif answer["status"] == "deny":
            decision = {
                "behavior": "deny",
                "message": answer.get("message")
                or "The user denied this in the Trigger Point Office.",
            }
        else:
            continue
        print(
            json.dumps(
                {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": decision}}
            )
        )
        return


def telemetry(d):
    event = d.get("hook_event_name")
    tool = short_tool(d.get("tool_name"))
    kinds = {
        "PreToolUse": ("tool_started", f"Called {tool}"),
        "PostToolUse": ("tool_finished", f"Finished {tool}"),
        "PostToolUseFailure": ("tool_failed", f"{tool} failed"),
        "SubagentStart": ("agent_started", f"{d.get('agent_type')} started"),
        "SubagentStop": ("agent_stopped", f"{d.get('agent_type')} finished"),
        "SessionEnd": ("session_ended", "Claude Code session ended"),
    }
    if event not in kinds:
        return
    if event.startswith(("Pre", "Post")) and not str(d.get("tool_name", "")).startswith(
        ("mcp__trigger_point__", "mcp__claude_ai_", "Agent", "Task")
    ):
        return
    kind, summary = kinds[event]
    call(
        "/hook/event",
        {
            "kind": kind,
            "summary": summary[:240],
            "mission_id": mission_of(d),
            "session_id": d.get("session_id"),
            "agent_id": d.get("agent_id"),
            "role": d.get("agent_type"),
            "tool": tool or None,
        },
    )


def main():
    try:
        d = json.loads(sys.stdin.read() or "{}")
        if d.get("hook_event_name") == "PermissionRequest":
            name = str(d.get("tool_name", ""))
            if name.startswith("mcp__trigger_point__") or name in GUARDED:
                permission(d)
            return 0
        guarded = d.get("hook_event_name") == "PreToolUse" and d.get("tool_name") in GUARDED
        if guarded and guard(d["tool_name"], d.get("tool_input")):
            return 0
        telemetry(d)
    except (OSError, ValueError, KeyError, urllib.error.URLError):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
