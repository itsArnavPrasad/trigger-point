"""What Claude Code itself reports about its connectors. Read-only, cached, and off the request
path, because `claude mcp list` checks every server and takes many seconds."""

from __future__ import annotations

import re
import shutil
import subprocess
import threading
import time

REFRESH_SECONDS = 300
_LINE = re.compile(r"^(?P<name>.+?): .*? - (?P<state>.+)$")


def parse_mcp_list(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = _LINE.match(line.strip())
        if not m:
            continue
        state = m.group("state")
        if "Connected" in state:
            out[m.group("name")] = "connected"
        elif "Failed" in state:
            out[m.group("name")] = "failed"
        elif "Needs auth" in state:
            out[m.group("name")] = "needs_auth"
        elif "Not configured" in state:
            out[m.group("name")] = "not_configured"
    return out


class ConnectorStatus:
    def __init__(self) -> None:
        self._states: dict[str, str] = {}
        self._checked_at = 0.0
        self._running = False
        self._lock = threading.Lock()

    def states(self) -> dict[str, str]:
        """Returns the last result at once, and refreshes in the background when it is old."""
        with self._lock:
            stale = time.monotonic() - self._checked_at > REFRESH_SECONDS or not self._checked_at
            if stale and not self._running:
                self._running = True
                threading.Thread(target=self._refresh, daemon=True).start()
            return dict(self._states)

    def _refresh(self) -> None:
        found: dict[str, str] = {}
        try:
            exe = shutil.which("claude")
            if exe:
                done = subprocess.run(  # noqa: S603 - fixed argv
                    [exe, "mcp", "list"], capture_output=True, text=True, timeout=120, check=False
                )
                found = parse_mcp_list(done.stdout)
        except (OSError, subprocess.SubprocessError):
            found = {}
        with self._lock:
            self._states, self._checked_at, self._running = found, time.monotonic(), False
