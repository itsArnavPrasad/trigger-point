"""SQLite persistence. Context versions are append-only; a saved version is never rewritten."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import TYPE_CHECKING

from trigger_point.models.context import BusinessContext
from trigger_point.models.run import RunReceipt

if TYPE_CHECKING:
    from trigger_point.cases.models import AccountCase
    from trigger_point.drafts.models import CampaignDraft
    from trigger_point.mission.models import Mission
    from trigger_point.mission.service import DiscoveryRun
    from trigger_point.research.service import ResearchRun

SCHEMA = """
CREATE TABLE IF NOT EXISTS contexts (
    id TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    body TEXT NOT NULL,
    PRIMARY KEY (id, version)
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    mode TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS missions (
    id TEXT PRIMARY KEY,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS discoveries (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_runs (
    id TEXT PRIMARY KEY,
    discovery_id TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cases (
    research_id TEXT NOT NULL,
    account_id INTEGER NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (research_id, account_id)
);
CREATE TABLE IF NOT EXISTS drafts (
    id TEXT PRIMARY KEY,
    research_id TEXT NOT NULL,
    account_id INTEGER NOT NULL,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_pages (
    run_id TEXT NOT NULL,
    url TEXT NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (run_id, url)
);
"""


class VersionConflict(RuntimeError):
    pass


class Store:
    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        with closing(self._connect()) as conn, conn:
            conn.executescript(SCHEMA)

    @property
    def path(self) -> str:
        return self._path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def insert_context_version(self, context_id: str, ctx: BusinessContext) -> None:
        try:
            with closing(self._connect()) as conn, conn:
                conn.execute(
                    "INSERT INTO contexts (id, version, status, body) VALUES (?, ?, ?, ?)",
                    (context_id, ctx.version, ctx.status, ctx.model_dump_json()),
                )
        except sqlite3.IntegrityError as exc:
            raise VersionConflict(f"{context_id} v{ctx.version} already exists") from exc

    def get_context(self, context_id: str, version: int | None = None) -> BusinessContext | None:
        query = "SELECT body FROM contexts WHERE id = ?"
        params: tuple[object, ...] = (context_id,)
        if version is not None:
            query += " AND version = ?"
            params += (version,)
        query += " ORDER BY version DESC LIMIT 1"
        with closing(self._connect()) as conn:
            row = conn.execute(query, params).fetchone()
        return BusinessContext.model_validate_json(row[0]) if row else None

    def list_context_versions(self, context_id: str) -> list[tuple[int, str, str]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT version, status, created_at FROM contexts WHERE id = ? ORDER BY version",
                (context_id,),
            ).fetchall()
        return [(int(v), str(s), str(c)) for v, s, c in rows]

    def save_run(self, run: RunReceipt) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO runs (id, kind, mode, body) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET body = excluded.body",
                (run.id, run.kind, run.mode, run.model_dump_json()),
            )

    def get_run(self, run_id: str) -> RunReceipt | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT body FROM runs WHERE id = ?", (run_id,)).fetchone()
        return RunReceipt.model_validate_json(row[0]) if row else None

    def list_runs(self) -> list[RunReceipt]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT body FROM runs ORDER BY rowid").fetchall()
        return [RunReceipt.model_validate_json(r[0]) for r in rows]

    def list_missions(self, limit: int = 50) -> list[Mission]:
        from trigger_point.mission.models import Mission

        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT body FROM missions ORDER BY rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        return [Mission.model_validate_json(r[0]) for r in rows]

    def list_discoveries(self, limit: int = 50) -> list[DiscoveryRun]:
        from trigger_point.mission.service import DiscoveryRun

        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT body FROM discoveries ORDER BY rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        return [DiscoveryRun.model_validate_json(r[0]) for r in rows]

    def save_run_pages(self, run_id: str, pages: dict[str, str]) -> None:
        with closing(self._connect()) as conn, conn:
            conn.executemany(
                "INSERT OR REPLACE INTO run_pages (run_id, url, text) VALUES (?, ?, ?)",
                [(run_id, url, text) for url, text in pages.items()],
            )

    def save_mission(self, mission: Mission) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO missions (id, body) VALUES (?, ?) "
                "ON CONFLICT(id) DO UPDATE SET body = excluded.body",
                (mission.id, mission.model_dump_json()),
            )

    def get_mission(self, mission_id: str) -> Mission | None:
        from trigger_point.mission.models import Mission

        with closing(self._connect()) as conn:
            row = conn.execute("SELECT body FROM missions WHERE id = ?", (mission_id,)).fetchone()
        return Mission.model_validate_json(row[0]) if row else None

    def save_discovery(self, run: DiscoveryRun) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO discoveries (id, mission_id, body) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET body = excluded.body",
                (run.id, run.mission_id, run.model_dump_json()),
            )

    def get_discovery(self, discovery_id: str) -> DiscoveryRun | None:
        from trigger_point.mission.service import DiscoveryRun

        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT body FROM discoveries WHERE id = ?", (discovery_id,)
            ).fetchone()
        return DiscoveryRun.model_validate_json(row[0]) if row else None

    def save_research(self, run: ResearchRun) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO research_runs (id, discovery_id, body) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET body = excluded.body",
                (run.id, run.discovery_id, run.model_dump_json()),
            )

    def get_research(self, research_id: str) -> ResearchRun | None:
        from trigger_point.research.service import ResearchRun

        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT body FROM research_runs WHERE id = ?", (research_id,)
            ).fetchone()
        return ResearchRun.model_validate_json(row[0]) if row else None

    def list_research(self, limit: int = 50) -> list[ResearchRun]:
        from trigger_point.research.service import ResearchRun

        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT body FROM research_runs ORDER BY rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        return [ResearchRun.model_validate_json(r[0]) for r in rows]

    def save_case(self, case: AccountCase) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT OR REPLACE INTO cases (research_id, account_id, body) VALUES (?, ?, ?)",
                (case.research_id, case.account_id, case.model_dump_json()),
            )

    def get_case(self, research_id: str, account_id: int) -> AccountCase | None:
        from trigger_point.cases.models import AccountCase

        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT body FROM cases WHERE research_id = ? AND account_id = ?",
                (research_id, account_id),
            ).fetchone()
        return AccountCase.model_validate_json(row[0]) if row else None

    def save_draft(self, draft: CampaignDraft) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO drafts (id, research_id, account_id, body) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET body = excluded.body",
                (draft.id, draft.research_id, draft.account_id, draft.model_dump_json()),
            )

    def get_draft(self, draft_id: str) -> CampaignDraft | None:
        from trigger_point.drafts.models import CampaignDraft

        with closing(self._connect()) as conn:
            row = conn.execute("SELECT body FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        return CampaignDraft.model_validate_json(row[0]) if row else None

    def list_drafts(self, research_id: str | None = None, limit: int = 100) -> list[CampaignDraft]:
        from trigger_point.drafts.models import CampaignDraft

        query = "SELECT body FROM drafts"
        params: tuple[object, ...] = ()
        if research_id is not None:
            query, params = query + " WHERE research_id = ?", (research_id,)
        with closing(self._connect()) as conn:
            rows = conn.execute(query + " ORDER BY rowid DESC LIMIT ?", (*params, limit)).fetchall()
        return [CampaignDraft.model_validate_json(r[0]) for r in rows]
