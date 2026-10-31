"""The mission workflow's MCP tools. Thin by design: every rule lives in the engine and service.
Tools in WORKFLOW_APPROVAL_TOOLS are under `permissions.ask`, so Claude Code puts the exact call
in front of a human before it runs."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from trigger_point.context.horizon import horizon_from_goal
from trigger_point.context.service import IntakeBrief
from trigger_point.workflow.feedback import FeedbackService
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
        brief = IntakeBrief(
            product_description, target_geography, time_horizon or horizon_from_goal(goal)
        )
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

    @server.tool(annotations=WRITES)
    def target_from_account(mission_id: str, account_id: int, audience: str) -> dict[str, Any]:
        """Make a qualified, researched account an outreach target. Its why-now comes from its own
        research signals, so the learning loop can learn which signals work. A rejected account is
        refused."""
        return wf.target_from_account(mission_id, account_id, audience)

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
        verify their current employer and rescore. In live mode it also looks up their business
        email and phone (about 3 credits per person matched). Those details are for the user to see;
        they never enter evidence, drafts or prompts."""
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


def register_feedback_tools(server: MCPServer, fb: FeedbackService) -> None:
    """Reading what came back and recording it. No tool here approves or decides anything."""

    @server.tool(annotations=READ_ONLY)
    def list_open_threads(mission_id: str) -> dict[str, Any]:
        """Gmail threads to read. Call get_thread on each with PLAIN_TEXT, then sync_replies."""
        return fb.open_threads(mission_id)

    @server.tool(annotations=WRITES)
    def sync_replies(mission_id: str) -> dict[str, Any]:
        """Turn the threads you just read into replies. Trigger Point takes sender and text from the
        captured Gmail response, so there is nothing to type in."""
        return fb.sync_replies(mission_id)

    @server.tool(annotations=WRITES)
    def import_meeting(
        mission_id: str, source_id: str, suggested_account: str | None = None
    ) -> dict[str, Any]:
        """Import a Wispr meeting you read with get_meeting, by its id. A suggested account is
        only a suggestion: unless a calendar id or a target's name proves it, a person decides.
        If it answers `incomplete`, call get_meeting again with view_transcript.start_char set to
        `continue_from`, then import again."""
        return fb.import_meeting(mission_id, source_id, suggested_account)

    @server.tool(annotations=WRITES)
    def add_meeting_insights(
        mission_id: str, meeting_id: str, insights: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Each insight: kind (pain, desired_outcome, objection, alternative, budget, urgency,
        buying_process, success_criteria, commitment, next_step), text, basis (statement or
        interpretation), quote, speaker, ambiguous. A statement needs a verbatim quote from the
        transcript, or it is refused. An interpretation goes to a person for review."""
        return fb.add_insights(mission_id, meeting_id, insights)

    @server.tool(annotations=READ_ONLY)
    def get_learning_inputs(mission_id: str) -> dict[str, Any]:
        """Reviewed insights and real outcomes, for finding what repeats across sources."""
        return fb.learning_inputs(mission_id)

    @server.tool(annotations=WRITES)
    def propose_lesson(
        mission_id: str,
        text: str,
        target: Literal["icp", "messaging", "qualification", "channel"],
        evidence_ids: list[str],
    ) -> dict[str, Any]:
        """Suggest a candidate lesson, citing insight or outcome ids. A person decides in the
        Office. One source can be stored but never approved."""
        return fb.propose_lesson(mission_id, text, target, evidence_ids)

    @server.tool(annotations=WRITES)
    def propose_campaign_plan(
        mission_id: str,
        summary: str,
        changes: list[dict[str, Any]],
        campaign: dict[str, Any],
    ) -> dict[str, Any]:
        """Propose the next campaign from what was learned. Each change is {text, target
        (icp|messaging|qualification|channel), evidence_ids, experiment, dimension?, value?};
        campaign is {audience, signal_type, angle, why}. A change backed by one source must set
        experiment true. A person approves in the Office; nothing changes until then."""
        return fb.propose_campaign_plan(mission_id, summary, changes, campaign)

    @server.tool(annotations=WRITES)
    def write_follow_up(mission_id: str, outreach_id: str) -> dict[str, Any]:
        """The next message in a sequence, verified like any other. Stops if they answered."""
        return fb.write_follow_up(mission_id, outreach_id)


def register_conversation_tools(server: MCPServer, conv: Any, zone: Any) -> None:
    """Moving a conversation along. What to say and when to meet is decided in code, not here:
    these tools hand the Director exact values and record what happened."""

    @server.tool(annotations=READ_ONLY)
    def prepare_reply(mission_id: str, target_id: str) -> dict[str, Any]:
        """The exact reply to send: to, subject, body, replyThreadId. Send it with Gmail
        send_message exactly as given, then call record_reply_sent."""
        return dict(conv.prepare_reply(mission_id, target_id))

    @server.tool(annotations=WRITES)
    def record_reply_sent(mission_id: str, target_id: str, message_id: str) -> dict[str, Any]:
        """Record the Gmail message id of the reply you just sent."""
        return dict(conv.record_reply_sent(mission_id, target_id, message_id))

    @server.tool(annotations=READ_ONLY)
    def get_booking(mission_id: str, target_id: str) -> dict[str, Any]:
        """The meeting to put on the calendar: title (starts with a code), attendee, start, end.
        Create exactly that Google Calendar event with a Google Meet link."""
        minutes, tz = zone(mission_id)
        return dict(conv.get_booking(mission_id, target_id, minutes, tz))

    @server.tool(annotations=WRITES)
    def record_booked_meeting(
        mission_id: str, target_id: str, token: str, event_id: str, meet_link: str
    ) -> dict[str, Any]:
        """After the calendar event exists: its id and Meet link. Adds the meeting to the
        dashboard with prep notes and queues the confirmation reply."""
        minutes, tz = zone(mission_id)
        return dict(
            conv.record_booked_meeting(
                mission_id, target_id, token, event_id, meet_link, minutes, tz
            )
        )

    @server.tool(annotations=WRITES)
    def record_busy_times(mission_id: str, busy: list[dict[str, Any]]) -> dict[str, Any]:
        """After reading my Google Calendar for the next 14 days: every event as {start, end},
        ISO 8601 with a UTC offset. Include all-day, tentative and other people's invites I accepted.
        Trigger Point never offers or books a time that overlaps these."""
        return dict(conv.record_busy(mission_id, busy))
