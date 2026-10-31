"""FastAPI application factory. Dependencies are chosen once, from the explicit mode."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException

from trigger_point.cases.service import CaseService
from trigger_point.config import Settings, load_settings
from trigger_point.context.extractor import ContextExtractor, LlmContextExtractor
from trigger_point.context.service import ContextService
from trigger_point.drafts.service import DraftService
from trigger_point.llm.base import StructuredLlm
from trigger_point.llm.hyde import HydeStructuredLlm, default_llm_http_client
from trigger_point.llm.replay import ReplayStructuredLlm
from trigger_point.mission.service import DiscoveryService, MissionService
from trigger_point.providers.crustdata.client import CreditBudget, CrustdataClient
from trigger_point.providers.crustdata.replay import RecordingTransport, ReplayTransport
from trigger_point.research.service import ResearchService
from trigger_point.store.db import Store
from trigger_point.web.fetcher import Fetcher, FixtureFetcher, SafeHttpFetcher, default_http_client
from trigger_point.workflow.engine import MissionNotFound, WorkflowEngine
from trigger_point.workflow.service import WorkflowService
from trigger_point.workflow.store import WorkflowStore

CrustdataFactory = Callable[[CreditBudget], CrustdataClient]


@dataclass(frozen=True)
class AppDeps:
    fetcher: Fetcher
    extractor: ContextExtractor
    store: Store
    llm: StructuredLlm | None = None
    crustdata: CrustdataFactory | None = None


def build_llm(settings: Settings) -> StructuredLlm:
    if settings.provider_modes["llm"] == "replay":
        return ReplayStructuredLlm(Path(settings.fixtures_dir) / "llm")
    assert settings.hyde_api_key is not None  # enforced by load_settings in live mode
    return HydeStructuredLlm(
        default_llm_http_client(),
        settings.hyde_base_url,
        settings.hyde_api_key.get_secret_value(),
        settings.llm_model,
    )


def crustdata_factory(settings: Settings) -> CrustdataFactory:
    root = Path(settings.fixtures_dir) / "crustdata"

    def make(budget: CreditBudget) -> CrustdataClient:
        if settings.provider_modes["crustdata"] == "replay":
            http = httpx.Client(transport=ReplayTransport(root))
            return CrustdataClient(http, "replay-no-key", budget, mode="replay")
        assert settings.crustdata_api_key is not None  # enforced by load_settings
        transport: httpx.BaseTransport = httpx.HTTPTransport()
        record_dir = os.environ.get("CRUSTDATA_RECORD_DIR")
        if record_dir:
            transport = RecordingTransport(transport, Path(record_dir))
        http = httpx.Client(transport=transport, timeout=httpx.Timeout(30.0), trust_env=False)
        return CrustdataClient(
            http,
            settings.crustdata_api_key.get_secret_value(),
            budget,
            api_version=settings.crustdata_api_version,
        )

    return make


def research_reference_date(settings: Settings) -> date:
    """Live research is evaluated today; replay as of the fixtures' recording date, so
    freshness verdicts in a replayed demo match the day the data was captured."""
    if settings.provider_modes["crustdata"] == "live":
        return datetime.now(UTC).date()
    meta = Path(settings.fixtures_dir) / "crustdata" / "_meta.json"
    return date.fromisoformat(json.loads(meta.read_text())["reference_date"])


def default_deps(settings: Settings) -> AppDeps:
    root = Path(settings.fixtures_dir)
    fetcher: Fetcher = (
        SafeHttpFetcher(default_http_client())
        if settings.provider_modes["web"] == "live"
        else FixtureFetcher(root / "sites")
    )
    llm = build_llm(settings)
    return AppDeps(
        fetcher,
        LlmContextExtractor(llm),
        Store(settings.database_path),
        llm,
        crustdata_factory(settings),
    )


@dataclass(frozen=True)
class Services:
    """Everything a front end needs. The web UI and the MCP server share one instance shape."""

    settings: Settings
    store: Store
    contexts: ContextService
    missions: MissionService
    discovery: DiscoveryService
    research: ResearchService
    cases: CaseService
    drafts: DraftService
    workflow: WorkflowService


def build_services(settings: Settings, deps: AppDeps | None = None) -> Services:
    deps = deps or default_deps(settings)
    contexts = ContextService(deps.fetcher, deps.extractor, deps.store, settings.provider_modes)
    missions = MissionService(
        contexts, deps.llm or build_llm(settings), deps.store, settings.crustdata_run_credit_budget
    )
    discovery = DiscoveryService(
        missions, contexts, deps.store, deps.crustdata or crustdata_factory(settings)
    )
    research = ResearchService(
        deps.store,
        deps.crustdata or crustdata_factory(settings),
        settings.crustdata_run_credit_budget,
        reference_date=lambda: research_reference_date(settings),
        fetch_contacts=settings.crustdata_fetch_contacts,
    )
    cases = CaseService(deps.store)
    drafts = DraftService(deps.store, cases, deps.llm or build_llm(settings))
    engine = WorkflowEngine(WorkflowStore(deps.store.path))
    workflow = WorkflowService(
        engine,
        contexts,
        missions,
        discovery,
        research,
        cases,
        drafts,
        deps.store,
        settings,
        deps.llm or build_llm(settings),
    )
    return Services(
        settings, deps.store, contexts, missions, discovery, research, cases, drafts, workflow
    )


def create_app(settings: Settings, deps: AppDeps | None = None) -> FastAPI:
    services = build_services(settings, deps)
    app = FastAPI(title="Trigger Point")
    app.state.settings = settings
    app.state.services = services

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "mode": settings.run_mode,
            **{f"{p}_mode": m for p, m in settings.provider_modes.items()},
        }

    from trigger_point.api.routes_cases import cases_router
    from trigger_point.api.routes_context import context_router
    from trigger_point.api.routes_mission import mission_router

    app.include_router(context_router(services.contexts, services.store))
    app.include_router(cases_router(services.cases, services.drafts))
    app.include_router(mission_router(services.missions, services.discovery, services.research))

    @app.get("/api/workflow/missions")
    def list_workflow_missions() -> dict[str, object]:
        missions = services.workflow.engine.missions()
        return {"missions": [m.model_dump(mode="json") for m in missions]}

    @app.get("/api/workflow/missions/{mission_id}")
    def workflow_mission(mission_id: str) -> dict[str, object]:
        status = services.workflow.status(mission_id)
        if not status["ok"]:
            raise HTTPException(404, "unknown mission")
        return status

    @app.get("/api/workflow/missions/{mission_id}/events")
    def workflow_events(mission_id: str) -> dict[str, object]:
        try:
            services.workflow.engine.mission(mission_id)
        except MissionNotFound as exc:
            raise HTTPException(404, "unknown mission") from exc
        events = services.workflow.engine.events(mission_id)
        return {"events": [e.model_dump(mode="json") for e in events]}

    return app


def create_default_app() -> FastAPI:
    """Entry point: `uv run uvicorn trigger_point.api.app:create_default_app --factory`. The Office is
    installed here, so tests of the plain API do not need its token."""
    from trigger_point.office.routes import install_office

    app = create_app(load_settings())
    install_office(app, app.state.services)
    return app
