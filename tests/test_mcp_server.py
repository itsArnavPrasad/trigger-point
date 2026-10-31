"""The MCP server exposes the same services as the UI, attributed to Claude Code."""

from pathlib import Path
from typing import Any

import anyio

from tests.conftest import FIXTURES
from trigger_point.api.app import AppDeps, build_services
from trigger_point.config import load_settings
from trigger_point.context.extractor import LlmContextExtractor
from trigger_point.llm.replay import ReplayStructuredLlm
from trigger_point.mcp_server import APPROVAL_TOOLS, build_server
from trigger_point.store.db import Store
from trigger_point.web.fetcher import FixtureFetcher


def server(tmp_path: Path) -> Any:
    settings = load_settings({"DATABASE_URL": f"sqlite:///{tmp_path / 'm.db'}"})
    llm = ReplayStructuredLlm(FIXTURES / "llm")
    deps = AppDeps(
        FixtureFetcher(FIXTURES / "sites"), LlmContextExtractor(llm), Store(tmp_path / "m.db"), llm
    )
    return build_server(build_services(settings, deps))


def call(srv: Any, name: str, **args: Any) -> dict[str, Any]:
    async def go() -> Any:
        return await srv.call_tool(name, args)

    result = anyio.run(go)
    assert not result.is_error, result
    return dict(result.structured_content)


def test_only_workflow_tools_can_change_a_mission(tmp_path: Path) -> None:
    tools = {t.name: t for t in anyio.run(server(tmp_path).list_tools)}
    for gone in ("intake_website", "compile_mission", "run_discovery", "approve_draft"):
        assert gone not in tools
    assert tools["get_business_context"].annotations.read_only_hint is True
    for name in APPROVAL_TOOLS:
        assert "human" in (tools[name].description or "").lower()


def test_status_reports_modes(tmp_path: Path) -> None:
    assert call(server(tmp_path), "trigger_point_status")["provider_modes"]["crustdata"] == "replay"


def test_integration_health_is_a_tool(tmp_path: Path) -> None:
    states = {
        i["id"]: i["state"]
        for i in call(server(tmp_path), "get_integration_health")["integrations"]
    }
    assert states["wispr"] == "not_connected"


def test_every_prompt_has_a_version(tmp_path: Path) -> None:
    from trigger_point.office.views import prompt_versions

    versions = prompt_versions()
    assert set(versions) == {"context", "mission", "draft", "strategy", "outreach"}
    assert all(v.endswith("-v1") for v in versions.values())
