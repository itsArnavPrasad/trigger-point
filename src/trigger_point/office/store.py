"""The office's own tables, in Trigger Point's database: what hooks saw, held permissions, chat, costs.

Hooks and the MCP server run in separate processes from the API. SQLite is what they share."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

SCHEMA = """
CREATE TABLE IF NOT EXISTS office_activity (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id TEXT, session_id TEXT, agent_id TEXT, role TEXT,
    kind TEXT NOT NULL, tool TEXT, summary TEXT NOT NULL, at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS office_permissions (
    id TEXT PRIMARY KEY, seq INTEGER, mission_id TEXT, session_id TEXT, role TEXT,
    tool TEXT NOT NULL, input TEXT NOT NULL, status TEXT NOT NULL,
    message TEXT, at TEXT NOT NULL, decided_at TEXT
);
CREATE TABLE IF NOT EXISTS office_messages (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id TEXT NOT NULL, sender TEXT NOT NULL, text TEXT NOT NULL, at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS office_runs (
    mission_id TEXT PRIMARY KEY, session_id TEXT, status TEXT NOT NULL, detail TEXT,
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS office_costs (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id TEXT NOT NULL, source TEXT NOT NULL, amount REAL NOT NULL, unit TEXT NOT NULL,
    basis TEXT NOT NULL, ref TEXT UNIQUE, at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS office_changes (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, mission_id TEXT, at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class OfficeStore:
    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        with closing(self._conn()) as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _write(self, mission_id: str | None) -> Iterator[sqlite3.Connection]:
        """Every write also ticks the change log, which is what the live stream follows."""
        with closing(self._conn()) as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                yield c
                c.execute(
                    "INSERT INTO office_changes (mission_id, at) VALUES (?, ?)",
                    (mission_id, _now()),
                )
            except BaseException:
                c.rollback()
                raise
            c.commit()

    def _rows(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        with closing(self._conn()) as c:
            return [dict(r) for r in c.execute(sql, args).fetchall()]

    def latest_change(self) -> int:
        """The newest tick across this table and the workflow's event log."""
        rows = self._rows(
            "SELECT (SELECT COALESCE(MAX(seq), 0) FROM office_changes) "
            "+ (SELECT COUNT(*) FROM wf_events) AS n"
        )
        return int(rows[0]["n"])

    def touch(self, mission_id: str | None = None) -> None:
        with self._write(mission_id):
            pass

    # activity --------------------------------------------------------------------------------

    def add_activity(self, **row: Any) -> None:
        with self._write(row.get("mission_id")) as c:
            c.execute(
                "INSERT INTO office_activity "
                "(mission_id, session_id, agent_id, role, kind, tool, summary, at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row.get("mission_id"),
                    row.get("session_id"),
                    row.get("agent_id"),
                    row.get("role"),
                    row["kind"],
                    row.get("tool"),
                    row["summary"],
                    _now(),
                ),
            )

    def activity(self, mission_id: str, limit: int = 300) -> list[dict[str, Any]]:
        rows = self._rows(
            "SELECT * FROM office_activity WHERE mission_id = ? ORDER BY seq DESC LIMIT ?",
            mission_id,
            limit,
        )
        return list(reversed(rows))

    def mission_for_session(self, session_id: str) -> str | None:
        rows = self._rows(
            "SELECT mission_id FROM office_activity WHERE session_id = ? "
            "AND mission_id IS NOT NULL ORDER BY seq DESC LIMIT 1",
            session_id,
        )
        return rows[0]["mission_id"] if rows else None

    # permissions -----------------------------------------------------------------------------

    def open_permission(
        self,
        mission_id: str | None,
        session_id: str | None,
        role: str | None,
        tool: str,
        tool_input: dict[str, Any],
    ) -> str:
        pid = f"perm_{uuid4().hex[:16]}"
        with self._write(mission_id) as c:
            c.execute(
                "INSERT INTO office_permissions "
                "(id, mission_id, session_id, role, tool, input, status, at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
                (pid, mission_id, session_id, role, tool, json.dumps(tool_input), _now()),
            )
        return pid

    def permission(self, pid: str) -> dict[str, Any] | None:
        rows = self._rows("SELECT * FROM office_permissions WHERE id = ?", pid)
        return self._permission(rows[0]) if rows else None

    def _permission(self, row: dict[str, Any]) -> dict[str, Any]:
        return {**row, "input": json.loads(row["input"])}

    def pending_permissions(self, mission_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM office_permissions WHERE status = 'pending'"
        rows = (
            self._rows(sql + " AND mission_id = ? ORDER BY at", mission_id)
            if mission_id
            else self._rows(sql + " ORDER BY at")
        )
        return [self._permission(r) for r in rows]

    def decide_permission(self, pid: str, decision: str, message: str | None) -> bool:
        """First answer wins. A dialog cannot be answered twice."""
        current = self.permission(pid)
        with self._write(current["mission_id"] if current else None) as c:
            cur = c.execute(
                "UPDATE office_permissions SET status = ?, message = ?, decided_at = ? "
                "WHERE id = ? AND status = 'pending'",
                (decision, message, _now(), pid),
            )
            return cur.rowcount == 1

    # chat, runs, costs -----------------------------------------------------------------------

    def add_message(self, mission_id: str, sender: str, text: str) -> None:
        with self._write(mission_id) as c:
            c.execute(
                "INSERT INTO office_messages (mission_id, sender, text, at) VALUES (?, ?, ?, ?)",
                (mission_id, sender, text, _now()),
            )

    def messages(self, mission_id: str) -> list[dict[str, Any]]:
        return self._rows(
            "SELECT * FROM office_messages WHERE mission_id = ? ORDER BY seq", mission_id
        )

    def set_run(
        self, mission_id: str, status: str, session_id: str | None = None, detail: str | None = None
    ) -> None:
        with self._write(mission_id) as c:
            c.execute(
                "INSERT INTO office_runs (mission_id, session_id, status, detail, at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(mission_id) DO UPDATE SET "
                "status = excluded.status, detail = excluded.detail, at = excluded.at, "
                "session_id = COALESCE(excluded.session_id, office_runs.session_id)",
                (mission_id, session_id, status, detail, _now()),
            )

    def run(self, mission_id: str) -> dict[str, Any] | None:
        rows = self._rows("SELECT * FROM office_runs WHERE mission_id = ?", mission_id)
        return rows[0] if rows else None

    def add_cost(
        self, mission_id: str, source: str, amount: float, unit: str, basis: str, ref: str
    ) -> None:
        """`basis` is actual or estimated. `ref` makes a repeat of the same charge a no-op."""
        with self._write(mission_id) as c:
            c.execute(
                "INSERT OR IGNORE INTO office_costs "
                "(mission_id, source, amount, unit, basis, ref, at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (mission_id, source, amount, unit, basis, ref, _now()),
            )

    def costs(self, mission_id: str) -> list[dict[str, Any]]:
        return self._rows(
            "SELECT * FROM office_costs WHERE mission_id = ? ORDER BY seq", mission_id
        )
