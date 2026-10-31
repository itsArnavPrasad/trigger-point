"""Mission compile/approve and Crustdata discovery runs."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from trigger_point.context.service import ContextService
from trigger_point.llm.base import LlmError, LlmRequest, StructuredLlm
from trigger_point.mission.compiler import (
    compile_plan,
    compile_search_request,
    favour_signals,
    relaxation_steps,
)
from trigger_point.mission.models import GTMPlan, Mission, MissionDraft
from trigger_point.mission.prompt import MISSION_SYSTEM_PROMPT, build_mission_message
from trigger_point.mission.selection import RejectedCompany, select_accounts
from trigger_point.models.context import Mode
from trigger_point.providers.crustdata.client import (
    CallReceipt,
    CreditBudget,
    CrustdataClient,
    estimate_search_credits,
)
from trigger_point.providers.crustdata.errors import CrustdataError
from trigger_point.providers.crustdata.identity import Ambiguous, Resolved, resolve_identity
from trigger_point.providers.crustdata.models import Company, CompanySearchRequest
from trigger_point.store.db import Store


class ContextNotApproved(RuntimeError):
    pass


class MissionNotFound(LookupError):
    pass


class MissionNotApproved(RuntimeError):
    pass


class MissionCompileFailed(RuntimeError):
    pass


class DiscoveryFailed(RuntimeError):
    def __init__(self, message: str, discovery_id: str) -> None:
        super().__init__(message)
        self.discovery_id = discovery_id


def _now() -> datetime:
    return datetime.now(UTC)


class MissionService:
    def __init__(
        self,
        contexts: ContextService,
        llm: StructuredLlm,
        store: Store,
        credit_budget: float,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._contexts, self._llm, self._store = contexts, llm, store
        self._budget, self._clock = credit_budget, clock

    def compile(
        self,
        context_id: str,
        initiated_by: str = "ui",
        lessons: str = "",
        favoured_signals: list[str] | None = None,
    ) -> Mission:
        ctx = self._contexts.get(context_id)
        if ctx.status != "approved":
            raise ContextNotApproved(f"context {context_id} v{ctx.version} is {ctx.status}")
        req = LlmRequest(
            task="mission_compile",
            replay_key=ctx.domain,
            system=MISSION_SYSTEM_PROMPT,
            user=build_mission_message(ctx) + lessons,
            schema=MissionDraft,
            max_tokens=8000,
        )
        try:
            resp = self._llm.complete(req)
            plan = compile_plan(resp.output, seller_domain=ctx.domain, credit_budget=self._budget)
            plan = favour_signals(plan, favoured_signals or [])
            search = compile_search_request(plan)
        except (LlmError, ValueError) as exc:
            raise MissionCompileFailed(str(exc)) from exc
        mission = Mission(
            id=uuid.uuid4().hex,
            context_id=context_id,
            context_version=ctx.version,
            user_goal=ctx.user_goal,
            plan=plan,
            search_request=search.to_body(),
            estimated_credits=str(estimate_search_credits(search)),
            mode=resp.mode,
            llm_mode=resp.mode,
            created_at=self._clock(),
            initiated_by=initiated_by,
        )
        self._store.save_mission(mission)
        return mission

    def get(self, mission_id: str) -> Mission:
        mission = self._store.get_mission(mission_id)
        if mission is None:
            raise MissionNotFound(mission_id)
        return mission

    def revise(self, mission_id: str, changes: dict[str, object]) -> Mission:
        """A reviewer's edit to the plan. It recompiles the search and needs approval again."""
        current = self.get(mission_id)
        plan = GTMPlan.model_validate({**current.plan.model_dump(), **changes})
        search = compile_search_request(plan)
        revised = current.model_copy(
            update={
                "plan": plan,
                "search_request": search.to_body(),
                "estimated_credits": str(estimate_search_credits(search)),
                "status": "review_required",
                "approved_at": None,
            }
        )
        self._store.save_mission(revised)
        return revised

    def approve(self, mission_id: str) -> Mission:
        mission = self.get(mission_id).model_copy(
            update={"status": "approved", "approved_at": self._clock()}
        )
        self._store.save_mission(mission)
        return mission


class CallRecord(BaseModel):
    endpoint: str
    method: str
    mode: Mode
    ok: bool
    status_code: int | None
    credits_used: str | None
    estimated_credits: str
    attempts: int
    latency_ms: int
    cache_hit: bool
    result_count: int | None
    replay_source: str | None
    error_kind: str | None
    error_message: str | None
    started_at: datetime

    @classmethod
    def from_receipt(cls, r: CallReceipt) -> CallRecord:
        d: dict[str, Any] = asdict(r)
        d["credits_used"] = None if r.credits_used is None else str(r.credits_used)
        d["estimated_credits"] = str(r.estimated_credits)
        return cls.model_validate({k: d[k] for k in cls.model_fields})


class DiscoveryRun(BaseModel):
    id: str
    mission_id: str
    mode: Mode
    initiated_by: str = "ui"
    started_at: datetime
    finished_at: datetime | None = None
    outcome: Literal["running", "completed", "completed_empty", "failed"] = "running"
    seller_identity: str | None = None
    relaxations: list[str] = Field(default_factory=list)
    accounts: list[Company] = Field(default_factory=list)
    rejected: list[RejectedCompany] = Field(default_factory=list)
    calls: list[CallRecord] = Field(default_factory=list)
    credits: dict[str, str] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class DiscoveryService:
    def __init__(
        self,
        missions: MissionService,
        contexts: ContextService,
        store: Store,
        client_factory: Callable[[CreditBudget], CrustdataClient],
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._missions, self._contexts, self._store = missions, contexts, store
        self._factory, self._clock = client_factory, clock

    def run(self, mission_id: str, initiated_by: str = "ui") -> DiscoveryRun:
        mission = self._missions.get(mission_id)
        if mission.status != "approved":
            raise MissionNotApproved(mission_id)
        seller_domain = self._contexts.get(mission.context_id, mission.context_version).domain
        budget = CreditBudget(mission.plan.credit_budget)
        client = self._factory(budget)
        run = DiscoveryRun(
            id=uuid.uuid4().hex,
            mission_id=mission_id,
            mode=client.mode,
            started_at=self._clock(),
            initiated_by=initiated_by,
        )
        try:
            self._discover(run, client, mission, seller_domain)
        except CrustdataError as exc:
            run.outcome = "failed"
            run.errors.append(str(exc))
        finally:
            run.calls = [CallRecord.from_receipt(r) for r in client.receipts]
            run.credits = {
                "actual": str(budget.spent),
                "unconfirmed_estimate": str(budget.unconfirmed),
                "budget": str(budget.limit),
            }
            run.finished_at = self._clock()
            self._store.save_discovery(run)
        if run.outcome == "failed":
            raise DiscoveryFailed(run.errors[-1], run.id)
        return run

    def _discover(
        self, run: DiscoveryRun, client: CrustdataClient, mission: Mission, seller_domain: str
    ) -> None:
        access = client.endpoint_access(path="/company/search").data
        if not access.is_enabled("/company/search"):
            raise CrustdataError("permission", "/company/search is not enabled for this API key")
        seller_id: int | None = None
        result = client.identify_domains([seller_domain]).data
        resolution = resolve_identity(result[0], seller_domain) if result else None
        if isinstance(resolution, Resolved):
            seller_id = resolution.company_id
            run.seller_identity = f"resolved to Crustdata company {seller_id}"
        elif isinstance(resolution, Ambiguous):
            run.seller_identity = f"ambiguous: {resolution.reason}; excluded by domain only"
        else:
            run.seller_identity = "not found in Crustdata; excluded by domain only"
        request = CompanySearchRequest.model_validate(mission.search_request)
        page = client.search_companies(request).data
        if not page.companies:
            for step in relaxation_steps(mission.plan):
                run.relaxations.append(step.description)
                page = client.search_companies(compile_search_request(step.plan)).data
                if page.companies:
                    break
        run.accounts, run.rejected = select_accounts(
            page.companies, mission.plan, seller_domain, seller_id
        )
        run.outcome = "completed" if run.accounts else "completed_empty"

    def get(self, discovery_id: str) -> DiscoveryRun | None:
        return self._store.get_discovery(discovery_id)

    def for_mission(self, mission_id: str) -> list[DiscoveryRun]:
        return [d for d in self._store.list_discoveries() if d.mission_id == mission_id]
