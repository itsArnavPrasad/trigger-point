"""The mission workflow's MCP tools. Thin by design: every rule lives in the engine and service.
Tools in WORKFLOW_APPROVAL_TOOLS are under `permissions.ask`, so Claude Code puts the exact call
in front of a human before it runs."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from trigger_point.context.service import IntakeBrief
from trigger_point.workflow.service import WorkflowService

WORKFLOW_APPROVAL_TOOLS = (
    "approve_business_profile",
    "approve_icp_plan",
    "discover_accounts",
    "research_account_signals",
    "map_buying_committee",
    "approve_campaign_draft",
)
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITES = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True)


def register_workflow_tools(server: MCPServer, wf: WorkflowService) -> None:  # noqa: C901
    @server.tool(annotations=WRITES)
    def create_mission(
        website_url: str,
        goal: str,
        product_description: str = "",
        target_geography: str = "",
        time_horizon: str = "",
    ) -> dict[str, Any]:
        """Start a mission from a website and a revenue goal: reads the site (max 8 pages,
        SSRF-guarded) and drafts the business profile. The same request returns the open
        mission. Every later tool takes the returned mission_id. A product description is
        recorded as a user statement, which also rescues a site that cannot be read."""
        brief = IntakeBrief(product_description, target_geography, time_horizon)
        return wf.create_mission(website_url, goal, brief)

    @server.tool(annotations=WRITES)
    def request_user_approval(
        mission_id: str, gate: Literal["business_profile", "icp_plan", "campaign_draft"]
    ) -> dict[str, Any]:
        """Put the current profile, plan or draft up for human review. Trigger Point computes what is
        being approved and returns its hash; a caller cannot choose it."""
        return wf.request_user_approval(mission_id, gate)

    @server.tool(annotations=WRITES)
    def approve_business_profile(
        mission_id: str, approval_id: str, acknowledge_unsupported: bool = False
    ) -> dict[str, Any]:
        """HUMAN APPROVAL REQUIRED: only call after the human reviewed this exact version.
        Unsupported claims block approval unless acknowledged, which drops them."""
        return wf.approve_business_profile(mission_id, approval_id, acknowledge_unsupported)

    @server.tool(annotations=WRITES)
    def edit_business_profile(mission_id: str, field: str, values: list[str]) -> dict[str, Any]:
        """Replace one profile field with the user's words, during review. New text is recorded
        as a user statement. Creates a new version, which needs approval again."""
        return wf.edit_business_profile(mission_id, field, values)

    @server.tool(annotations=READ_ONLY)
    def prepare_test_send(mission_id: str, outreach_id: str) -> dict[str, Any]:
        """The exact recipient, subject and body for a test email. Use these values unchanged."""
        return wf.prepare_test_send(mission_id, outreach_id)

    @server.tool(annotations=WRITES)
    def record_test_send(
        mission_id: str, outreach_id: str, to: str, message_id: str, thread_id: str
    ) -> dict[str, Any]:
        """Record a test email Gmail really sent, using the ids it returned."""
        return wf.record_test_send(mission_id, outreach_id, to, message_id, thread_id)

    @server.tool(annotations=WRITES)
    def record_test_meeting(
        mission_id: str, title: str, held_on: str, account_name: str, event_id: str, link: str
    ) -> dict[str, Any]:
        """Record a test meeting the calendar really created, using the ids it returned."""
        fields = {
            "title": title,
            "held_on": held_on,
            "account_name": account_name,
            "event_id": event_id,
            "link": link,
        }
        return wf.record_test_meeting(mission_id, fields)

    @server.tool(annotations=WRITES)
    def build_strategy(mission_id: str) -> dict[str, Any]:
        """From the approved profile: market map, value proposition, positioning, GTM motion,
        channel plan and experiments, all labelled as hypotheses and checked by code."""
        return wf.build_strategy(mission_id)

    @server.tool(annotations=WRITES)
    def build_icp(mission_id: str) -> dict[str, Any]:
        """Turn the approved profile into an ICP and an exact Crustdata search, listing
        assumptions and an upper-bound credit estimate. Spends no Crustdata credits."""
        return wf.build_icp(mission_id)

    @server.tool(annotations=WRITES)
    def approve_icp_plan(mission_id: str, approval_id: str) -> dict[str, Any]:
        """HUMAN APPROVAL REQUIRED: only call after the human reviewed the plan and the credit
        estimate. Allows discovery to spend up to the run budget."""
        return wf.approve_icp_plan(mission_id, approval_id)

    @server.tool(annotations=WRITES)
    def discover_accounts(mission_id: str) -> dict[str, Any]:
        """HUMAN APPROVAL REQUIRED (spends Crustdata credits): find target companies for the
        approved plan. Returns candidates and rejections with reasons. Zero results is an
        honest answer: the mission waits for input."""
        return wf.discover_accounts(mission_id)

    @server.tool(annotations=WRITES)
    def research_account_signals(mission_id: str) -> dict[str, Any]:
        """HUMAN APPROVAL REQUIRED (spends Crustdata credits): collect dated job postings and
        metrics, record each as evidence with its source and date, and pre-score every account."""
        return wf.research_account_signals(mission_id)

    @server.tool(annotations=WRITES)
    def map_buying_committee(mission_id: str) -> dict[str, Any]:
        """HUMAN APPROVAL REQUIRED (spends Crustdata credits): find buyers at the top accounts,
        verify their current employer and rescore. Never fetches contact data."""
        return wf.map_buying_committee(mission_id)

    @server.tool(annotations=WRITES)
    def verify_evidence(mission_id: str) -> dict[str, Any]:
        """Audit every evidence record with deterministic rules (audit-v1): source, entity,
        date, freshness. Returns counts and each failure with its reason."""
        return wf.verify_evidence(mission_id)

    @server.tool(annotations=WRITES)
    def score_account(mission_id: str, account_id: int | None = None) -> dict[str, Any]:
        """Select the top qualified, contactable account with audited evidence and return its
        deterministic score-v1 breakdown and case file. Scores come from code only."""
        return wf.score_account(mission_id, account_id)

    @server.tool(annotations=WRITES)
    def draft_campaign(mission_id: str) -> dict[str, Any]:
        """Write the first-touch draft for the selected account from verified case evidence,
        checked by the outreach verifier. Nothing is sent, and there is no way to send."""
        return wf.draft_campaign(mission_id)

    @server.tool(annotations=WRITES)
    def run_quality_gate(mission_id: str) -> dict[str, Any]:
        """Run the deterministic last check on the draft: relevance, evidence, duplicates and
        policy rules. A failure stops the mission with the findings."""
        return wf.run_quality_gate(mission_id)

    @server.tool(annotations=WRITES)
    def approve_campaign_draft(
        mission_id: str, approval_id: str, expected_hash: str
    ) -> dict[str, Any]:
        """HUMAN APPROVAL REQUIRED: only call after the human read this exact email
        (expected_hash = the target_hash they reviewed). Records approval; never sends."""
        return wf.approve_campaign_draft(mission_id, approval_id, expected_hash)

    @server.tool(annotations=WRITES)
    def reject_approval(mission_id: str, approval_id: str, reason: str) -> dict[str, Any]:
        """Record that the human rejected a review. The mission waits for input."""
        return wf.reject_approval(mission_id, approval_id, reason)

    @server.tool(annotations=WRITES)
    def cancel_mission(mission_id: str, reason: str) -> dict[str, Any]:
        """Stop a mission. Open tasks are cancelled and pending approvals expire."""
        return wf.cancel_mission(mission_id, reason)

    @server.tool(annotations=READ_ONLY)
    def get_mission_status(mission_id: str) -> dict[str, Any]:
        """The mission's state, mode, every task, pending approvals and what it is waiting for."""
        return wf.status(mission_id)

    @server.tool(annotations=READ_ONLY)
    def get_task_details(task_id: str) -> dict[str, Any]:
        """One task: role, status, attempts, output, error, its events and evidence ids."""
        return wf.task_details(task_id)
