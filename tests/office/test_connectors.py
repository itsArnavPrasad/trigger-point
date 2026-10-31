"""Connector state comes from what Claude Code reports, never from what Trigger Point hopes."""

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
