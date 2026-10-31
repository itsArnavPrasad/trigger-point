"""SQLite persistence for the workflow, in Trigger Point's database. Every state change and its events
commit in one transaction, so the log can never disagree with the state it describes."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path

from trigger_point.workflow.icp import IcpVersion
from trigger_point.workflow.models import (
    TERMINAL,
    EvidenceRecord,
    WorkflowApproval,
    WorkflowEvent,
    WorkflowMission,
    WorkflowTask,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS wf_missions (
    id TEXT PRIMARY KEY,
    request_key TEXT NOT NULL,
    open INTEGER NOT NULL,
    body TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS wf_one_open_request ON wf_missions (request_key) WHERE open = 1;
CREATE TABLE IF NOT EXISTS wf_tasks (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    body TEXT NOT NULL,
    UNIQUE (mission_id, position)
);
CREATE TABLE IF NOT EXISTS wf_approvals (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wf_evidence (
    mission_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (mission_id, evidence_id)
);
CREATE TABLE IF NOT EXISTS wf_icp_versions (
    mission_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (mission_id, version)
);
CREATE TABLE IF NOT EXISTS gtm_records (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    id TEXT NOT NULL UNIQUE,
    mission_id TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wf_events (
    event_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    body TEXT NOT NULL,
    delivered_at TEXT,
    UNIQUE (mission_id, seq)
);
"""


class Tx:
    """Reads and writes on one connection. Use through `WorkflowStore.tx` or `.view`."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._c = conn

    def open_mission(self, request_key: str) -> WorkflowMission | None:
        row = self._c.execute(
            "SELECT body FROM wf_missions WHERE request_key = ? AND open = 1", (request_key,)
        ).fetchone()
        return WorkflowMission.model_validate_json(row[0]) if row else None

    def mission(self, mission_id: str) -> WorkflowMission | None:
        row = self._c.execute("SELECT body FROM wf_missions WHERE id = ?", (mission_id,)).fetchone()
        return WorkflowMission.model_validate_json(row[0]) if row else None

    def missions(self, limit: int) -> list[WorkflowMission]:
        rows = self._c.execute(
            "SELECT body FROM wf_missions ORDER BY rowid DESC LIMIT ?", (limit,)
        ).fetchall()
        return [WorkflowMission.model_validate_json(r[0]) for r in rows]

    def save_mission(self, m: WorkflowMission, request_key: str | None = None) -> None:
        is_open = 0 if m.state in TERMINAL else 1
        if request_key is not None:
            self._c.execute(
                "INSERT INTO wf_missions (id, request_key, open, body) VALUES (?, ?, ?, ?)",
                (m.id, request_key, is_open, m.model_dump_json()),
            )
            return
        self._c.execute(
            "UPDATE wf_missions SET open = ?, body = ? WHERE id = ?",
            (is_open, m.model_dump_json(), m.id),
        )

    def task(self, task_id: str) -> WorkflowTask | None:
        row = self._c.execute("SELECT body FROM wf_tasks WHERE id = ?", (task_id,)).fetchone()
        return WorkflowTask.model_validate_json(row[0]) if row else None

    def tasks(self, mission_id: str) -> list[WorkflowTask]:
        rows = self._c.execute(
            "SELECT body FROM wf_tasks WHERE mission_id = ? ORDER BY position", (mission_id,)
        ).fetchall()
        return [WorkflowTask.model_validate_json(r[0]) for r in rows]

    def save_task(self, t: WorkflowTask) -> None:
        self._c.execute(
            "INSERT INTO wf_tasks (id, mission_id, position, body) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET body = excluded.body",
            (t.id, t.mission_id, t.position, t.model_dump_json()),
        )

    def approval(self, approval_id: str) -> WorkflowApproval | None:
        row = self._c.execute(
            "SELECT body FROM wf_approvals WHERE id = ?", (approval_id,)
        ).fetchone()
        return WorkflowApproval.model_validate_json(row[0]) if row else None

    def approvals(self, mission_id: str) -> list[WorkflowApproval]:
        rows = self._c.execute(
            "SELECT body FROM wf_approvals WHERE mission_id = ? ORDER BY rowid", (mission_id,)
        ).fetchall()
        return [WorkflowApproval.model_validate_json(r[0]) for r in rows]

    def save_approval(self, a: WorkflowApproval) -> None:
        self._c.execute(
            "INSERT INTO wf_approvals (id, mission_id, body) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET body = excluded.body",
            (a.id, a.mission_id, a.model_dump_json()),
        )

    def evidence(self, mission_id: str) -> list[EvidenceRecord]:
        rows = self._c.execute(
            "SELECT body FROM wf_evidence WHERE mission_id = ? ORDER BY rowid", (mission_id,)
        ).fetchall()
        return [EvidenceRecord.model_validate_json(r[0]) for r in rows]

    def add_evidence(self, mission_id: str, record: EvidenceRecord) -> bool:
        cur = self._c.execute(
            "INSERT OR IGNORE INTO wf_evidence (mission_id, evidence_id, body) VALUES (?, ?, ?)",
            (mission_id, record.id, record.model_dump_json()),
        )
        return cur.rowcount == 1

    def update_evidence(self, mission_id: str, record: EvidenceRecord) -> None:
        self._c.execute(
            "UPDATE wf_evidence SET body = ? WHERE mission_id = ? AND evidence_id = ?",
            (record.model_dump_json(), mission_id, record.id),
        )

    def icp_versions(self, mission_id: str) -> list[IcpVersion]:
        rows = self._c.execute(
            "SELECT body FROM wf_icp_versions WHERE mission_id = ? ORDER BY version", (mission_id,)
        ).fetchall()
        return [IcpVersion.model_validate_json(r[0]) for r in rows]

    def save_icp(self, icp: IcpVersion) -> None:
        self._c.execute(
            "INSERT INTO wf_icp_versions (mission_id, version, body) VALUES (?, ?, ?) "
            "ON CONFLICT(mission_id, version) DO UPDATE SET body = excluded.body",
            (icp.mission_id, icp.version, icp.model_dump_json()),
        )

    def save_record(self, kind: str, record_id: str, mission_id: str, body: str) -> None:
        self._c.execute(
            "INSERT INTO gtm_records (kind, id, mission_id, body) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET body = excluded.body",
            (kind, record_id, mission_id, body),
        )

    def records(self, kind: str, mission_id: str) -> list[str]:
        rows = self._c.execute(
            "SELECT body FROM gtm_records WHERE kind = ? AND mission_id = ? ORDER BY seq",
            (kind, mission_id),
        ).fetchall()
        return [str(r[0]) for r in rows]

    def all_records(self, kind: str) -> list[str]:
        rows = self._c.execute(
            "SELECT body FROM gtm_records WHERE kind = ? ORDER BY seq", (kind,)
        ).fetchall()
        return [str(r[0]) for r in rows]

    def next_seq(self, mission_id: str) -> int:
        row = self._c.execute(
            "SELECT COALESCE(MAX(seq), 0) FROM wf_events WHERE mission_id = ?", (mission_id,)
        ).fetchone()
        return int(row[0]) + 1

    def has_event(self, event_id: str) -> bool:
        row = self._c.execute("SELECT 1 FROM wf_events WHERE event_id = ?", (event_id,)).fetchone()
        return row is not None

    def add_event(self, e: WorkflowEvent) -> None:
        self._c.execute(
            "INSERT INTO wf_events (event_id, mission_id, seq, body) VALUES (?, ?, ?, ?)",
            (e.event_id, e.mission_id, e.seq, e.model_dump_json()),
        )

    def events(self, mission_id: str) -> list[WorkflowEvent]:
        rows = self._c.execute(
            "SELECT body FROM wf_events WHERE mission_id = ? ORDER BY seq", (mission_id,)
        ).fetchall()
        return [WorkflowEvent.model_validate_json(r[0]) for r in rows]

    def undelivered(self, limit: int) -> list[WorkflowEvent]:
        rows = self._c.execute(
            "SELECT body FROM wf_events WHERE delivered_at IS NULL ORDER BY rowid LIMIT ?",
            (limit,),
        ).fetchall()
        return [WorkflowEvent.model_validate_json(r[0]) for r in rows]

    def mark_delivered(self, event_ids: list[str], at: datetime) -> None:
        self._c.executemany(
            "UPDATE wf_events SET delivered_at = ? WHERE event_id = ?",
            [(at.isoformat(), eid) for eid in event_ids],
        )


class WorkflowStore:
    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        with closing(self._connect()) as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=30, isolation_level=None)

    @contextmanager
    def tx(self) -> Iterator[Tx]:
        """A write transaction. BEGIN IMMEDIATE serialises writers across processes (the MCP
        server and the web UI), which is what makes task claims and seq numbers safe."""
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield Tx(conn)
            except BaseException:
                conn.rollback()
                raise
            conn.commit()

    @contextmanager
    def view(self) -> Iterator[Tx]:
        with closing(self._connect()) as conn:
            yield Tx(conn)
