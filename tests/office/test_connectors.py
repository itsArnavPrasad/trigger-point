"""Connector state comes from what Claude Code reports, never from what Trigger Point hopes."""

import time

import pytest

from trigger_point.office import connectors
from trigger_point.office.connectors import parse_mcp_list

SAMPLE = """Checking MCP server health…

claude.ai Gmail: https://gmailmcp.googleapis.com/mcp/v1 - ✔ Connected
plugin:crustdata:crustdata: https://install.crustdata.com/mcp (HTTP) - ✔ Connected
plugin:sales:hubspot: https://mcp.hubspot.com/anthropic (HTTP) - ✘ Failed to connect — Incompatible
plugin:sales:slack: https://mcp.slack.com/mcp (HTTP) - ! Needs authentication
plugin:sales:gmail:  (HTTP) - - Not configured
"""


def test_parses_each_state() -> None:
    got = parse_mcp_list(SAMPLE)
    assert got["claude.ai Gmail"] == "connected"
    assert got["plugin:sales:hubspot"] == "failed"
    assert got["plugin:sales:slack"] == "needs_auth"
    assert got["plugin:sales:gmail"] == "not_configured"


def test_a_status_is_unchecked_until_a_check_has_finished(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        connectors.shutil, "which", lambda _name: None
    )  # no claude here: ends at once
    status = connectors.ConnectorStatus()
    assert status.checked is False and status.checking is False
    status.refresh_now()
    for _ in range(200):
        if status.checked and not status.checking:
            break
        time.sleep(0.02)
    assert status.checked and not status.checking
