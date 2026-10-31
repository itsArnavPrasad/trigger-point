"""A real Trigger Point behind the real MCP server, over replay fixtures, with one seam: a transport
that lets a test change what the Crustdata API answers."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio
import httpx
import pytest

from tests.conftest import FIXTURES
from trigger_point.api.app import AppDeps, Services, build_services
from trigger_point.config import load_settings
from trigger_point.context.extractor import LlmContextExtractor
from trigger_point.llm.replay import ReplayStructuredLlm
from trigger_point.mcp_server import build_server
from trigger_point.providers.crustdata.client import CreditBudget, CrustdataClient
from trigger_point.providers.crustdata.replay import ReplayTransport
from trigger_point.store.db import Store
from trigger_point.web.fetcher import FixtureFetcher

URL, GOAL = "supportpilot.example", "Book meetings with B2B SaaS companies scaling support teams"
Answer = Callable[[httpx.Request], httpx.Response | None]


class Provider(httpx.BaseTransport):
    """Replay, unless the test's `answer` has something else to say for this request."""

    def __init__(self) -> None:
        self.inner = ReplayTransport(FIXTURES / "crustdata")
        self.answer: Answer = lambda _r: None
        self.paths: list[str] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        return self.answer(request) or self.inner.handle_request(request)


@dataclass
class Rig:
    server: Any
    services: Services
    provider: Provider

    def call(self, name: str, **args: Any) -> dict[str, Any]:
        async def go() -> Any:
            return await self.server.call_tool(name, args)

        result = anyio.run(go)
        assert not result.is_error, result
        return dict(result.structured_content)

    def tools(self) -> dict[str, Any]:
        return {t.name: t for t in anyio.run(self.server.list_tools)}

    def event_types(self, mission_id: str) -> list[str]:
        return [e.event_type for e in self.services.workflow.engine.events(mission_id)]


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    settings = load_settings({"DATABASE_URL": f"sqlite:///{tmp_path / 'wf.db'}"})
    llm = ReplayStructuredLlm(FIXTURES / "llm")
    provider = Provider()

    def client(budget: CreditBudget) -> CrustdataClient:
        http = httpx.Client(transport=provider)
        return CrustdataClient(http, "replay-no-key", budget, mode="replay", sleep=lambda _s: None)

    deps = AppDeps(
        FixtureFetcher(FIXTURES / "sites"),
        LlmContextExtractor(llm),
        Store(tmp_path / "wf.db"),
        llm,
        client,
    )
    services = build_services(settings, deps)
    return Rig(build_server(services), services, provider)


def error_body(kind: str = "rate_limit_error") -> dict[str, Any]:
    return {"error": {"type": kind, "message": "provider says no", "metadata": []}}


def advance_to_accounts(rig: Rig) -> str:
    """Intake, profile approval, ICP and plan approval. The next step is discovery."""
    created = rig.call("create_mission", website_url=URL, goal=GOAL)
    mid = created["mission_id"]
    a = rig.call("request_user_approval", mission_id=mid, gate="business_profile")
    rig.call(
        "approve_business_profile",
        mission_id=mid,
        approval_id=a["approval_id"],
        acknowledge_unsupported=True,
    )
    assert rig.call("build_strategy", mission_id=mid)["ok"]
    assert rig.call("build_icp", mission_id=mid)["ok"]
    a = rig.call("request_user_approval", mission_id=mid, gate="icp_plan")
    rig.call("approve_icp_plan", mission_id=mid, approval_id=a["approval_id"])
    return str(mid)


def advance_to_draft(rig: Rig) -> str:
    mid = advance_to_accounts(rig)
    for tool in ("discover_accounts", "research_account_signals", "map_buying_committee"):
        assert rig.call(tool, mission_id=mid)["ok"], tool
    assert rig.call("verify_evidence", mission_id=mid)["ok"]
    assert rig.call("score_account", mission_id=mid)["ok"]
    assert rig.call("draft_campaign", mission_id=mid)["ok"]
    return mid


def json_body(request: httpx.Request) -> Any:
    return json.loads(request.content) if request.content else None
