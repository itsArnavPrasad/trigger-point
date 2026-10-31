"""Trigger Point MCP server: the typed tools Claude Code uses to run a mission.

Everything that changes a mission goes through the workflow tools, so the state machine, approval
gates and budgets always apply. The tools here only read. Tools listed in `APPROVAL_TOOLS` are
under `permissions.ask` in .claude/settings.json: Claude Code holds each call until a human
answers in the Trigger Point Office.

Run: `uv run python -m trigger_point.mcp_server` (stdio). Registered in the project's .mcp.json.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from trigger_point.api.app import Services, build_services
from trigger_point.cases.service import CaseNotFound
from trigger_point.config import load_settings
from trigger_point.context.service import ContextNotFound
from trigger_point.drafts.service import DraftNotFound
from trigger_point.models.context import CLAIM_LIST_FIELDS, BusinessContext
from trigger_point.office.views import integration_health
from trigger_point.research.service import ResearchNotFound
from trigger_point.workflow.mcp_tools import (
    WORKFLOW_APPROVAL_TOOLS,
    register_feedback_tools,
    register_workflow_tools,
)

APPROVAL_TOOLS = WORKFLOW_APPROVAL_TOOLS
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)

INSTRUCTIONS = """\
Trigger Point runs an evidence-first GTM mission. Rules: never invent facts, sources or companies; \
report unsupported claims as unsupported; a human answers every gated tool in the Trigger Point Office. \
SQLite is the system of record and the Office is the only UI."""


def _context_summary(cid: str, ctx: BusinessContext) -> dict[str, Any]:
    return {
        "ok": True,
        "context_id": cid,
        "version": ctx.version,
        "status": ctx.status,
        "mode": ctx.mode,
        "company": ctx.company_name.text if ctx.company_name else None,
        "claim_counts": {f: len(getattr(ctx, f)) for f in CLAIM_LIST_FIELDS},
        "unsupported_claims": [
            {"field": f, "text": c.text, "reason": c.status_reason}
            for f, c in ctx.iter_claims()
            if c.status == "unsupported"
        ],
        "clarification_questions": ctx.clarification_questions,
        "unknowns": ctx.unknowns,
    }


def build_server(services: Services) -> MCPServer:
    server = MCPServer("trigger_point", instructions=INSTRUCTIONS)
    contexts, discovery = services.contexts, services.discovery

    @server.tool(annotations=READ_ONLY)
    def trigger_point_status() -> dict[str, Any]:
        """Show which providers are live or fixture, and the per-run credit budget."""
        s = services.settings
        return {
            "provider_modes": s.provider_modes,
            "run_mode": s.run_mode,
            "llm_model": s.llm_model,
            "crustdata_run_credit_budget": s.crustdata_run_credit_budget,
        }

    @server.tool(annotations=READ_ONLY)
    def get_integration_health() -> dict[str, Any]:
        """Each connector: state, access and last success. Never says connected without a path."""
        return {"integrations": integration_health(services)}

    @server.tool(annotations=READ_ONLY)
    def get_business_context(context_id: str, version: int | None = None) -> dict[str, Any]:
        """Return every claim of a business context with kind (fact/inference/user_provided),
        grounding status, source URL and quoted excerpt."""
        try:
            ctx = contexts.get(context_id, version)
        except ContextNotFound:
            return {"ok": False, "error": "not_found"}
        claims = {
            f: [
                {
                    "text": c.text,
                    "kind": c.kind,
                    "status": c.status,
                    "source_url": c.source_url,
                    "excerpt": c.excerpt,
                }
                for c in getattr(ctx, f)
            ]
            for f in CLAIM_LIST_FIELDS
        }
        return {**_context_summary(context_id, ctx), "claims": claims}

    @server.tool(annotations=READ_ONLY)
    def get_discovery(discovery_id: str) -> dict[str, Any]:
        """Return a discovery run: accounts, rejections, provider calls and credits."""
        run = discovery.get(discovery_id)
        if run is None:
            return {"ok": False, "error": "not_found"}
        return _discovery_summary(run.model_dump(mode="json"))

    @server.tool(annotations=READ_ONLY)
    def get_research(research_id: str) -> dict[str, Any]:
        """Return a research run's ranked account board."""
        try:
            return _research_summary(services.research.get(research_id).model_dump(mode="json"))
        except ResearchNotFound:
            return {"ok": False, "error": "not_found"}

    @server.tool(annotations=READ_ONLY)
    def get_account_case(research_id: str, account_id: int) -> dict[str, Any]:
        """Return the account's case file: why account / person / now / us, each item a cited
        fact, a labelled inference or an unknown; route, next action and coverage gaps."""
        try:
            case = services.cases.get_or_build(research_id, account_id)
        except CaseNotFound as exc:
            return {"ok": False, "error": "not_found", "message": str(exc)}
        dump = case.model_dump(mode="json", exclude={"evidence", "score"})
        return {
            "ok": True,
            **dump,
            "score_total": case.score.total,
            "evidence": [
                {
                    "id": e.id,
                    "claim": e.claim,
                    "source_url": e.source_url,
                    "event_on": e.event_on.isoformat() if e.event_on else None,
                    "as_of": e.as_of.isoformat() if e.as_of else None,
                }
                for e in case.evidence
            ],
        }

    @server.tool(annotations=READ_ONLY)
    def get_draft(draft_id: str) -> dict[str, Any]:
        """Return a draft with its claim map, verifier log, status and content hash."""
        try:
            return _draft_summary(services.drafts.get(draft_id).model_dump(mode="json"))
        except DraftNotFound:
            return {"ok": False, "error": "not_found"}

    register_workflow_tools(server, services.workflow)
    register_feedback_tools(server, services.feedback)
    return server


def _research_summary(run: dict[str, Any]) -> dict[str, Any]:
    rid = run["id"]
    return {
        "ok": run["outcome"] != "failed",
        "research_id": rid,
        "outcome": run["outcome"],
        "mode": run["mode"],
        "reference_date": run["reference_date"],
        "notes": run["notes"],
        "credits": run["credits"],
        "errors": run["errors"],
        "accounts": [
            {
                "name": a["account"]["name"],
                "provider_company_id": a["account"]["provider_company_id"],
                "status": a["score"]["status"],
                "tier": a["score"]["tier"],
                "total": a["score"]["total"],
                "rejections": a["score"]["rejections"],
                "active_signals": [
                    s["description"] for s in a["signals"] if s["status"] == "active"
                ],
                "buyer": (
                    f"{a['best_person']['person']['name']}, "
                    f"{a['best_person']['person']['current_title']}"
                    if a["best_person"]
                    else None
                ),
            }
            for a in run["accounts"]
        ],
    }


def _draft_summary(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "draft_id": d["id"],
        "status": d["status"],
        "sending": d["sending"],
        "to": f"{d['recipient_name']}, {d['recipient_title']} at {d['account_name']}",
        "subject": d["subject"],
        "body": d["body"],
        "content_hash": d["content_hash"],
        "verifier_log": d["verifier_log"],
    }


def _discovery_summary(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": run["outcome"] != "failed",
        "discovery_id": run["id"],
        "outcome": run["outcome"],
        "mode": run["mode"],
        "seller_identity": run["seller_identity"],
        "relaxations": run["relaxations"],
        "accounts": [
            {
                k: a[k]
                for k in (
                    "name",
                    "primary_domain",
                    "provider_company_id",
                    "employee_count_range",
                    "headcount_growth_6m_pct",
                    "hiring_openings",
                    "hq_country",
                    "provider_updated_at",
                )
            }
            for a in run["accounts"]
        ],
        "rejected": run["rejected"],
        "credits": run["credits"],
        "errors": run["errors"],
    }


def main() -> None:
    build_server(build_services(load_settings())).run("stdio")


if __name__ == "__main__":
    main()
