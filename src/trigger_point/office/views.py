"""Read models for the dashboards. Everything comes from stored records; absent data stays absent.

One function builds one mission's whole view, so the UI never has to assemble truth itself."""

from __future__ import annotations

import shutil
from typing import Any

from trigger_point.api.app import Services
from trigger_point.context import prompt as context_prompt
from trigger_point.drafts import prompt as draft_prompt
from trigger_point.mission import prompt as mission_prompt
from trigger_point.office.store import OfficeStore
from trigger_point.research.service import AccountResearch, ResearchRun
from trigger_point.workflow import outreach, strategy
from trigger_point.workflow.gtm import build_pipeline, finance_metrics, propose_changes
from trigger_point.workflow.models import TASK_PLAN, TERMINAL

ROLES: tuple[tuple[str, str, str], ...] = (
    ("mission-director", "Mission Director", "Runs the mission and asks you when needed"),
    ("icp-strategist", "ICP Strategist", "Who to sell to, and why"),
    ("account-scout", "Account Scout", "Finds target companies"),
    ("signal-analyst", "Signal Analyst", "Finds dated reasons to act now"),
    ("buying-committee-mapper", "Buying Committee Mapper", "Finds the people involved"),
    ("evidence-auditor", "Evidence Auditor", "Checks claims against sources and scores"),
    ("campaign-architect", "Campaign Architect", "Drafts outreach from verified evidence"),
    ("quality-gatekeeper", "Quality Gatekeeper", "Last check before you review"),
)
# Stakeholder role from title, deterministic and labelled as an inference in the UI.
ROLE_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Economic buyer", ("chief", "ceo", "cfo", "coo", "cto", "cio", "president", "founder")),
    ("Executive sponsor", ("vp", "vice president", "svp", "evp")),
    ("Functional owner", ("head of", "director")),
    ("Champion", ("manager", "lead")),
)
GATE_DASHBOARD = {
    "business_profile": "icp-strategist",
    "icp_plan": "icp-strategist",
    "campaign_draft": "campaign-architect",
}
TOOL_ROLE = {
    "approve_business_profile": "icp-strategist",
    "approve_icp_plan": "icp-strategist",
    "discover_accounts": "account-scout",
    "research_account_signals": "signal-analyst",
    "map_buying_committee": "buying-committee-mapper",
    "approve_campaign_draft": "campaign-architect",
    "mcp__claude_ai_Gmail__send_message": "campaign-architect",
    "mcp__claude_ai_Google_Calendar__create_event": "mission-director",
}
SIGNAL_STATUS = {
    "verified": "VERIFIED",
    "user_provided": "VERIFIED",
    "stale": "STALE",
    "undated": "NEEDS_REVIEW",
    "entity_mismatch": "NEEDS_REVIEW",
    "unverifiable": "NEEDS_REVIEW",
    "unverified": "NEEDS_REVIEW",
}


def stakeholder_role(title: str | None) -> str:
    low = f" {(title or '').lower()} "
    for role, words in ROLE_WORDS:
        if any(w in low for w in words):
            return role
    return "End user or practitioner"


# Who to approach and why, nearest the problem first. Deterministic and labelled as a suggestion.
STAKEHOLDER_PLAN: dict[str, tuple[int, str, str]] = {
    "Champion": (1, "Learn how the problem shows up day to day", "A short working session"),
    "Functional owner": (2, "Confirm the problem is a priority", "A 20-minute review"),
    "End user or practitioner": (3, "Check the workflow fits", "A look at their process"),
    "Executive sponsor": (4, "Tie it to a goal they own", "An introduction from the owner"),
    "Economic buyer": (5, "Agree the value is worth the budget", "A business case, later"),
}


def stakeholder_plan(title: str | None) -> dict[str, Any]:
    sequence, purpose, ask = STAKEHOLDER_PLAN[stakeholder_role(title)]
    return {"sequence": sequence, "purpose": purpose, "ask": ask}


def agent_status(
    role: str,
    tasks: list[dict[str, Any]],
    waiting: bool,
    ended: bool,
    director_waiting: bool = False,
) -> str:
    """Only what the tasks, open dialogs and the Director's turn say. No live work is idle."""
    mine = [t for t in tasks if t["role"] == role]
    if director_waiting and role == "mission-director" and not waiting:
        return "waiting_input"
    if waiting or any(t["status"] == "waiting_approval" for t in mine):
        return "waiting_approval"
    if any(t["status"] == "running" for t in mine):
        return "running"
    latest = [t for t in mine if t["status"] in ("succeeded", "failed")]
    if any(t["status"] == "failed" for t in latest):
        return "failed"
    if not ended and mine and any(t["status"] == "queued" for t in mine) and not latest:
        return "idle"
    return "succeeded" if latest else "idle"


def _profile(services: Services, context_id: str | None) -> dict[str, Any] | None:
    if context_id is None:
        return None
    ctx = services.contexts.get(context_id)
    from trigger_point.models.context import CLAIM_LIST_FIELDS

    groups = {
        f: [c.model_dump(mode="json") for c in getattr(ctx, f)]
        for f in CLAIM_LIST_FIELDS
        if getattr(ctx, f)
    }
    return {
        "context_id": context_id,
        "version": ctx.version,
        "status": ctx.status,
        "company": ctx.company_name.text if ctx.company_name else None,
        "domain": ctx.domain,
        "goal": ctx.user_goal,
        "readability": ctx.readability,
        "target_geography": ctx.target_geography,
        "time_horizon": ctx.time_horizon,
        "claims": groups,
        "unknowns": ctx.unknowns,
        "questions": ctx.clarification_questions,
        "pages": [p.model_dump(mode="json") for p in ctx.pages],
        "versions": [
            {"version": v, "status": s, "at": at}
            for v, s, at in services.contexts.versions(context_id)
        ],
    }


def _stakeholders(ar: AccountResearch, personas: list[str]) -> list[dict[str, Any]]:
    people = []
    for m in [*([ar.best_person] if ar.best_person else []), *ar.other_matches]:
        p = m.person
        people.append(
            {
                "known": True,
                "name": p.name,
                "title": p.current_title,
                "role": stakeholder_role(p.current_title),
                **stakeholder_plan(p.current_title),
                "confidence": m.confidence,
                "employer_verified": m.employer_verified,
                "reason": m.reason,
                "why": m.persona_why,
                "profile_url": p.profile_url,
            }
        )
    found = {m["title"] for m in people}
    for title in personas:
        if title not in found and ar.people_searched:
            people.append(
                {
                    "known": False,
                    "title": title,
                    "role": stakeholder_role(title),
                    **stakeholder_plan(title),
                }
            )
    return sorted(people, key=lambda s: s["sequence"])


def _accounts(run: ResearchRun | None, personas: list[str]) -> list[dict[str, Any]]:
    if run is None:
        return []
    rows = []
    for ar in run.accounts:
        a = ar.account
        rows.append(
            {
                "id": a.provider_company_id,
                "name": a.name,
                "domain": a.primary_domain,
                "country": a.hq_country,
                "size": a.employee_count_range,
                "industries": a.industries,
                "growth_6m": a.headcount_growth_6m_pct,
                "openings": a.hiring_openings,
                "score": ar.score.model_dump(mode="json"),
                "signals": [s.model_dump(mode="json") for s in ar.signals],
                "stakeholders": _stakeholders(ar, personas),
                "people_searched": ar.people_searched,
                "people_rejected": [r.model_dump(mode="json") for r in ar.people_rejected],
            }
        )
    return rows


def _funnel(
    services: Services, discovery_id: str | None, run: ResearchRun | None
) -> dict[str, Any]:
    discovery = services.store.get_discovery(discovery_id) if discovery_id else None
    if discovery is None:
        return {}
    scores = [a.score.status for a in run.accounts] if run else []
    return {
        "found": len(discovery.accounts) + len(discovery.rejected),
        "removed": len(discovery.rejected),
        "kept": len(discovery.accounts),
        "qualified": scores.count("qualified"),
        "insufficient": scores.count("insufficient_evidence"),
        "rejected": scores.count("rejected"),
        "awaiting": len(discovery.accounts) - len(scores),
        "removed_accounts": [r.model_dump(mode="json") for r in discovery.rejected],
        "relaxations": discovery.relaxations,
        "calls": [c.model_dump(mode="json") for c in discovery.calls],
        "credits": discovery.credits,
    }


def _costs(office: OfficeStore, mission_id: str, credits: dict[str, str] | None) -> dict[str, Any]:
    rows = office.costs(mission_id)
    return {
        "entries": rows,
        "claude_usd": round(sum(r["amount"] for r in rows if r["unit"] == "USD"), 4),
        "crustdata_credits": credits or {},
    }


HARNESS_CONNECTORS = (
    ("Gmail", "claude.ai Gmail", "Sends test emails to the test inbox"),
    ("Google Calendar", "claude.ai Google Calendar", "Books test meetings"),
    ("Google Sheets", "claude.ai Google Sheets", "Would export accounts"),
    ("Crustdata plugin", "plugin:crustdata:crustdata", "Claude Code only, bypasses the adapter"),
    ("HubSpot", "plugin:sales:hubspot", "Would be the CRM"),
    ("Salesforce", "plugin:sales:salesforce", "Would be the CRM"),
    ("Fireflies", "plugin:sales:fireflies", "Would read meeting notes"),
    ("Gong", "plugin:sales:gong", "Would read call notes"),
)


WIRED_CONNECTORS = {"claude.ai Gmail", "claude.ai Google Calendar"}


def harness_connectors(states: dict[str, str]) -> list[dict[str, Any]]:
    """What Claude Code can reach. Being connected there does not mean Trigger Point uses it."""
    return [
        {
            "id": key,
            "name": name,
            "purpose": purpose,
            "state": states.get(key, "unknown"),
            "wired": key in WIRED_CONNECTORS,
        }
        for name, key, purpose in HARNESS_CONNECTORS
    ]


def integration_health(services: Services) -> list[dict[str, Any]]:
    """Declares each connector honestly. `state` never says connected without a real path."""
    s = services.settings
    modes = s.provider_modes
    runs = [r for r in services.store.list_runs() if r.outcome != "failed" and r.pages_ok]
    last_web = runs[-1].finished_at.isoformat() if runs and runs[-1].finished_at else None
    crust = "fixture" if modes["crustdata"] == "replay" else "untested"
    if modes["crustdata"] == "replay" and s.crustdata_api_key is None:
        crust = "no_key"
    return [
        {
            "id": "claude",
            "name": "Claude Code",
            "purpose": "Runs the agents",
            "state": "ready" if shutil.which("claude") else "missing",
            "access": "execute",
            "last_success": None,
        },
        {
            "id": "web",
            "name": "Website reader",
            "purpose": "Reads the seller's site",
            "state": "live" if modes["web"] == "live" else "fixture",
            "access": "read",
            "last_success": last_web,
        },
        {
            "id": "llm",
            "name": s.llm_model,
            "purpose": "Extraction, ICP, drafts",
            "state": "live" if modes["llm"] == "live" else "fixture",
            "access": "read",
            "last_success": None,
        },
        {
            "id": "crustdata",
            "name": "Crustdata",
            "purpose": "Companies, jobs, people",
            "state": crust,
            "access": "read",
            "last_success": None,
            "note": {
                "untested": "No live call has been verified",
                "no_key": "CRUSTDATA_API_KEY is empty, so only fixtures can run",
            }.get(crust, "Fixture data"),
        },
        {
            "id": "wispr",
            "name": "Wispr Flow",
            "purpose": "Meeting notes",
            "state": "not_connected",
            "access": "read",
            "last_success": None,
        },
        {
            "id": "crm",
            "name": "CRM",
            "purpose": "Pipeline",
            "state": "not_connected",
            "access": "none",
            "last_success": None,
        },
        {
            "id": "email",
            "name": "Email sending",
            "purpose": "Test inbox only. Real recipients are blocked",
            "state": "test_only" if s.test_recipients else "disabled",
            "access": "send to test inbox" if s.test_recipients else "none",
            "last_success": None,
        },
    ]


def _finance(
    services: Services, office: OfficeStore, mission_id: str, run: ResearchRun | None
) -> dict[str, Any]:
    wf = services.workflow
    claude = sum(c["amount"] for c in office.costs(mission_id) if c["unit"] == "USD")
    manual = wf.costs(mission_id)
    usd = [c for c in manual if c.get("currency") == "USD"]
    actual = claude + sum(float(c["amount"]) for c in usd if c.get("basis") == "actual")
    estimated = sum(float(c["amount"]) for c in usd if c.get("basis") == "estimated")
    scores = [a.score.status for a in run.accounts] if run else []
    meetings = sum(1 for o in wf.outcomes(mission_id) if o.kind == "meeting_held")
    return {
        "metrics": finance_metrics(
            actual, estimated, len(scores), scores.count("qualified"), meetings
        ),
        "manual": manual,
        "excluded_other_currency": len(manual) - len(usd),
    }


def prompt_versions() -> dict[str, str]:
    return {
        "context": context_prompt.PROMPT_VERSION,
        "mission": mission_prompt.PROMPT_VERSION,
        "draft": draft_prompt.PROMPT_VERSION,
        "strategy": strategy.PROMPT_VERSION,
        "outreach": outreach.PROMPT_VERSION,
    }


def mission_summary(services: Services) -> list[dict[str, Any]]:
    return [
        {"id": m.id, "state": m.state, "mode": m.mode, "website_url": m.website_url, "goal": m.goal}
        for m in services.workflow.engine.missions(50)
    ]


def mission_view(services: Services, office: OfficeStore, mission_id: str) -> dict[str, Any]:
    engine = services.workflow.engine
    m = engine.mission(mission_id)
    tasks = [t.model_dump(mode="json") for t in engine.tasks(mission_id)]
    events = [e.model_dump(mode="json") for e in engine.events(mission_id)]
    permissions = office.pending_permissions(mission_id)
    for p in permissions:
        p["dashboard"] = TOOL_ROLE.get(
            p["tool"].removeprefix("mcp__trigger_point__"), "mission-director"
        )
    activity = office.activity(mission_id)
    run = services.store.get_research(m.research_id) if m.research_id else None
    gtm = services.store.get_mission(m.gtm_mission_id) if m.gtm_mission_id else None
    personas = [p.title for p in gtm.plan.personas] if gtm else []
    waiting_roles = {p["dashboard"] for p in permissions}
    ended = m.state in TERMINAL
    run_row = office.run(mission_id)
    director_waiting = not ended and run_row is not None and run_row["status"] == "idle"
    agents = []
    for role, name, purpose in ROLES:
        mine = [t for t in tasks if t["role"] == role]
        current = next((t for t in mine if t["status"] in ("running", "waiting_approval")), None)
        recent = [
            e for e in events if e.get("role") == role and e["event_type"].startswith("tool.")
        ]
        agents.append(
            {
                "role": role,
                "name": name,
                "purpose": purpose,
                "status": agent_status(role, tasks, role in waiting_roles, ended, director_waiting),
                "task": current or (mine[-1] if mine else None),
                "tasks": mine,
                "step": recent[-1]["summary"] if recent else None,
                "tools": recent[-12:],
                "hook_activity": [a for a in activity if a["role"] == role][-12:],
            }
        )
    outcomes = services.workflow.outcomes(mission_id)
    artifacts = [e["data"] for e in events if e["event_type"] == "artifact.published"]
    case = next((a["body"] for a in reversed(artifacts) if a.get("kind") == "case_file"), None)
    draft = services.store.get_draft(m.draft_id) if m.draft_id else None
    gate = next((t["output"] for t in tasks if t["kind"] == "quality_gate" and t["output"]), None)
    failed_gate = next((t for t in tasks if t["kind"] == "quality_gate" and t["error"]), None)
    return {
        "mission": m.model_dump(mode="json"),
        "plan": [t.kind for t in TASK_PLAN],
        "tasks": tasks,
        "agents": agents,
        "permissions": permissions,
        "approvals": [
            {**a.model_dump(mode="json"), "dashboard": GATE_DASHBOARD[a.gate]}
            for a in engine.approvals(mission_id)
        ],
        "profile": _profile(services, m.context_id),
        "icp": [i.model_dump(mode="json") for i in engine.icp_versions(mission_id)],
        "funnel": _funnel(services, m.discovery_id, run),
        "accounts": _accounts(run, personas),
        "notes": run.notes if run else [],
        "evidence": [
            {**e.model_dump(mode="json"), "signal_status": SIGNAL_STATUS[e.verification_status]}
            for e in engine.evidence(mission_id)
        ],
        "case": case,
        "draft": draft.model_dump(mode="json") if draft else None,
        "gate": gate,
        "gate_error": failed_gate["error"] if failed_gate else None,
        "costs": _costs(office, mission_id, run.credits if run else None),
        "strategy": services.workflow.strategy_versions(mission_id),
        "targets": services.workflow.targets(mission_id),
        "outreach": services.workflow.outreach(mission_id),
        "meetings": services.workflow.meetings(mission_id),
        "pipeline": build_pipeline(outcomes),
        "outcomes": [o.model_dump(mode="json") for o in outcomes],
        "learning": {
            **propose_changes(outcomes),
            "decisions": services.workflow.proposals(mission_id),
        },
        "finance": _finance(services, office, mission_id, run),
        "messages": office.messages(mission_id),
        "run": run_row,
        "events": events[-250:],
    }
