"""Builds and caches one case file per (research run, account)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from trigger_point.cases.builder import build_case
from trigger_point.cases.models import AccountCase
from trigger_point.store.db import Store


class CaseNotFound(LookupError):
    pass


class CaseService:
    def __init__(self, store: Store, clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self._store, self._clock = store, clock

    def get_or_build(self, research_id: str, account_id: int) -> AccountCase:
        cached = self._store.get_case(research_id, account_id)
        if cached is not None:
            return cached
        run = self._store.get_research(research_id)
        if run is None:
            raise CaseNotFound(f"research run {research_id}")
        ar = next((a for a in run.accounts if a.account.provider_company_id == account_id), None)
        if ar is None:
            raise CaseNotFound(f"account {account_id} is not in research run {research_id}")
        mission = self._store.get_mission(run.mission_id)
        if mission is None:
            raise CaseNotFound(f"mission {run.mission_id}")
        ctx = self._store.get_context(mission.context_id, mission.context_version)
        if ctx is None or ctx.status != "approved":
            raise CaseNotFound("the mission's approved business context is missing")
        case = build_case(
            ar,
            mission.plan,
            ctx,
            mission.context_id,
            research_id,
            run.reference_date,
            self._clock(),
            run.mode,
        )
        self._store.save_case(case)
        return case
