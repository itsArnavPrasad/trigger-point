"""Mission Runner: one Claude Code Director per mission, driven from the Office.

It starts `claude --agent mission-director` in stream-json mode, passes chat to its stdin and
stores what comes back. If the process is gone, the next message resumes the same session.
Approvals are not handled here: they stay Claude Code permission prompts, held by the hook."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import IO, Any, Protocol

from trigger_point.office.store import OfficeStore

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Process(Protocol):
    stdin: IO[str] | None
    stdout: IO[str] | None

    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...


Spawn = Callable[[Sequence[str], dict[str, str]], Process]


def _spawn(cmd: Sequence[str], env: dict[str, str]) -> Process:
    return subprocess.Popen(  # noqa: S603 - fixed argv; user text goes through stdin as data
        list(cmd),
        cwd=PROJECT_ROOT,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def director_command(session_id: str | None, model: str, budget_usd: float) -> list[str]:
    cmd = [
        "claude",
        "--agent",
        "mission-director",
        "--settings",
        ".claude/settings.json",
        "--model",
        model,
        "--max-budget-usd",
        str(budget_usd),
        "-p",
        "--verbose",
        "--output-format",
        "stream-json",
        "--input-format",
        "stream-json",
    ]
    return [*cmd, "--resume", session_id] if session_id else cmd


class MissionRunner:
    def __init__(
        self,
        office: OfficeStore,
        spawn: Spawn = _spawn,
        model: str = "claude-sonnet-5-5",
        budget_usd: float = 5.0,
    ) -> None:
        self._office, self._spawn, self._model, self._budget = office, spawn, model, budget_usd
        self._procs: dict[str, Process] = {}
        self._lock = threading.Lock()

    def is_running(self, mission_id: str) -> bool:
        proc = self._procs.get(mission_id)
        return proc is not None and proc.poll() is None

    def send(self, mission_id: str, text: str) -> None:
        """Delivers text to the mission's Director, starting or resuming it if needed."""
        with self._lock:
            if not self.is_running(mission_id):
                self._start(mission_id)
            proc = self._procs[mission_id]
            assert proc.stdin is not None  # noqa: S101 - always piped
            line = {"type": "user", "message": {"role": "user", "content": text}}
            proc.stdin.write(json.dumps(line) + "\n")
            proc.stdin.flush()
        self._office.set_run(mission_id, "working")

    def _start(self, mission_id: str) -> None:
        run = self._office.run(mission_id)
        session_id = run["session_id"] if run else None
        env = {**os.environ, "TRIGGER_POINT_MISSION_ID": mission_id}
        cmd = director_command(session_id, self._model, self._budget)
        proc = self._spawn(cmd, env)
        self._procs[mission_id] = proc
        threading.Thread(target=self._read, args=(mission_id, proc), daemon=True).start()

    def _read(self, mission_id: str, proc: Process) -> None:
        assert proc.stdout is not None  # noqa: S101 - always piped
        for line in proc.stdout:
            try:
                self._handle(mission_id, json.loads(line))
            except (ValueError, KeyError, TypeError):
                continue
        self._office.set_run(mission_id, "stopped")

    def _handle(self, mission_id: str, msg: dict[str, Any]) -> None:
        kind = msg.get("type")
        if kind == "system" and msg.get("subtype") == "init":
            self._office.set_run(mission_id, "working", session_id=msg.get("session_id"))
        elif kind == "assistant" and not msg.get("parent_tool_use_id"):
            for block in msg["message"]["content"]:
                if block.get("type") == "text" and block["text"].strip():
                    self._office.add_message(mission_id, "director", block["text"].strip())
        elif kind == "result":
            cost = msg.get("total_cost_usd")
            if isinstance(cost, int | float):
                ref = f"claude:{msg.get('session_id')}:{msg.get('uuid') or msg.get('duration_ms')}"
                self._office.add_cost(mission_id, "Claude Code", float(cost), "USD", "actual", ref)
            self._office.set_run(mission_id, "idle", detail=msg.get("subtype"))

    def stop(self, mission_id: str) -> None:
        with self._lock:
            proc = self._procs.pop(mission_id, None)
        if proc is not None and proc.poll() is None:
            proc.terminate()
