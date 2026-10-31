"""Runs mission steps on Trigger Point's existing services and reports what really happened.

Each step claims its task, does the work, then records the outcome. Provider failures become
typed task failures; empty results stop and ask. Nothing here invents a value."""

from __future__ import annotations

import hashlib
import html
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Concatenate

from pydantic import ValidationError

from trigger_point.cases.models import AccountCase, CaseItem
from trigger_point.cases.service import CaseNotFound, CaseService
from trigger_point.config import Settings
from trigger_point.context.service import (
    ContextNotFound,
    ContextService,
    EmptyProfile,
    IntakeBrief,
    IntakeFailed,
    InvalidEdit,
    UnsupportedFactsRemain,
    VersionMismatch,
)
from trigger_point.drafts.models import CampaignDraft
from trigger_point.drafts.service import DraftFailed, DraftNotAllowed, DraftService, DraftStateError
from trigger_point.llm.base import LlmError, LlmRequest, StructuredLlm
from trigger_point.mission.models import Mission
from trigger_point.mission.service import (
    CallRecord,
    ContextNotApproved,
    DiscoveryFailed,
    DiscoveryService,
    MissionCompileFailed,
    MissionService,
)
from trigger_point.models.context import BusinessContext
from trigger_point.models.evidence import Evidence
from trigger_point.providers.crustdata.errors import RETRYABLE
from trigger_point.research.service import (
    AccountResearch,
    ResearchFailed,
    ResearchRun,
    ResearchService,
)
from trigger_point.security.url_guard import UnsafeUrlError, check_url_static, normalize_seed_url
from trigger_point.store.db import Store
from trigger_point.workflow.engine import (
    ApprovalMissing,
    InvalidTransition,
    MissionNotFound,
    TaskBusy,
    TaskNotFound,
    WorkflowEngine,
)
from trigger_point.workflow.gtm import Outcome, label_strategy
from trigger_point.workflow.icp import IcpVersion, build_icp
from trigger_point.workflow.loop import HOLDOUT_SHARE
from trigger_point.workflow.models import (
    ApprovalGate,
    EvidenceRecord,
    TaskKind,
    WorkflowMission,
    WorkflowTask,
    stable_id,
)
from trigger_point.workflow.outreach import (
    AUDIENCES,
    OUTREACH_VERSION,
    SAMPLE_TARGETS,
    OutreachWire,
    approved_facts,
    build_outreach_message,
    verify_outreach,
)
from trigger_point.workflow.outreach import PROMPT_VERSION as OUTREACH_PROMPT_VERSION
from trigger_point.workflow.outreach import SYSTEM_PROMPT as OUTREACH_PROMPT
from trigger_point.workflow.outreach import content_hash as outreach_hash
from trigger_point.workflow.strategy import PROMPT_VERSION as STRATEGY_PROMPT_VERSION
from trigger_point.workflow.strategy import SYSTEM_PROMPT as STRATEGY_PROMPT
from trigger_point.workflow.strategy import StrategyDraft, build_strategy_message
from trigger_point.workflow.verification import EvidenceCheck, audit_evidence, quality_gate

ACTOR = "claude-code"
ICP_EDITABLE = frozenset(
    {
        "icp_query",
        "countries",
        "employee_ranges",
        "excluded_domains",
        "tech_keywords",
        "max_accounts",
    }
)
HUMAN = "user (via Claude Code permission prompt)"
_PROVIDER_ERROR = re.compile(r"crustdata (\w+):")
Result = dict[str, Any]


class StepError(Exception):
    def __init__(self, kind: str, message: str, retryable: bool) -> None:
        super().__init__(message)
        self.kind, self.message, self.retryable = kind, message, retryable


@dataclass
class StepResult:
    output: dict[str, Any]
    summary: str
    artifact_ids: list[str] = field(default_factory=list)
    wait_reason: str | None = None


def guarded[S, **P](
    fn: Callable[Concatenate[S, P], Result],
) -> Callable[Concatenate[S, P], Result]:
    """Refusals are answers: the agent gets a typed reason, and the mission is unchanged."""

    def inner(self: S, /, *args: P.args, **kwargs: P.kwargs) -> Result:
        try:
            return fn(self, *args, **kwargs)
        except (MissionNotFound, TaskNotFound) as exc:
            return {"ok": False, "error": "not_found", "message": str(exc)}
        except InvalidTransition as exc:
            return {"ok": False, "error": "invalid_transition", "message": str(exc)}
        except TaskBusy as exc:
            return {"ok": False, "error": "task_busy", "message": str(exc)}
        except ApprovalMissing as exc:
            return {"ok": False, "error": "approval_missing", "message": str(exc)}

    return inner


def teach_modes(mission_mode: str) -> tuple[str, ...]:
    """A fixture mission can show the loop on fixture data. Nothing else ever teaches."""
    return ("replay",) if mission_mode == "replay" else ("live",)


def outcome_mode(mission_mode: str, fields: dict[str, Any]) -> str:
    """What an outcome is really about, whatever the mission's other providers were doing."""
    if mission_mode == "replay":
        return "replay"
    if str(fields.get("account_name") or "").startswith("SAMPLE"):
        return "test"
    return "replay" if mission_mode == "mixed" and fields.get("account_id") else "live"


def lessons_block(lessons: list[dict[str, Any]]) -> str:
    if not lessons:
        return ""
    lines = "\n".join(f"- {html.escape(x['text'], quote=False)}" for x in lessons)
    return f"\n<approved_lessons>\n{lines}\n</approved_lessons>"


def _variant(target_id: str) -> str:
    digest = hashlib.sha256(target_id.encode()).digest()[0]
    return "holdout" if digest % HOLDOUT_SHARE == 0 else "treatment"


def _provider_error(message: str) -> StepError:
    m = _PROVIDER_ERROR.search(message)
    kind = m.group(1) if m else "provider_error"
    # A missing recording or key is a gap to fill, not the end of the mission.
    return StepError(kind, message, kind in RETRYABLE or kind == "replay_missing")


def _record(e: Evidence, account: str | None) -> EvidenceRecord:
    return EvidenceRecord(
        id=e.id,
        account=account,
        entity_type=e.entity_type,
        claim=e.claim,
        source_url=e.source_url,
        provider_ref=e.provider_ref,
        publisher=e.publisher,
        event_on=e.event_on,
        as_of=e.as_of,
        retrieved_at=e.retrieved_at,
        excerpt=e.excerpt,
    )


def _items(items: list[CaseItem]) -> list[dict[str, Any]]:
    return [i.model_dump(mode="json") for i in items]


def _buyer(match: Any) -> dict[str, str]:
    """The person to write to, and their business email if Crustdata supplied one. This stays on
    the target record for the founder; it is never put in a prompt, a draft or an event."""
    if match is None or not match.person.name:
        return {}
    emails = [c for c in match.person.contact if c.kind == "email"]
    emails.sort(key=lambda c: c.label != "business")
    out = {"buyer_name": match.person.name, "buyer_title": match.person.current_title or ""}
    if emails:
        out["buyer_email"] = emails[0].value
    return out


def audience_for(industries: list[str]) -> str:
    """Who we are writing to, from what the account is. School-like accounts reach an authority."""
    text = " ".join(industries).casefold()
    return (
        "school_authority" if any(w in text for w in ("education", "school")) else "company_buyer"
    )


class WorkflowService:
    def __init__(
        self,
        engine: WorkflowEngine,
        contexts: ContextService,
        missions: MissionService,
        discovery: DiscoveryService,
        research: ResearchService,
        cases: CaseService,
        drafts: DraftService,
        store: Store,
        settings: Settings,
        llm: StructuredLlm,
    ) -> None:
        self.engine = engine
        self._llm = llm
        self.test_recipients = settings.test_recipients
        self.today: Callable[[], date] = lambda: datetime.now(UTC).date()
        self._contexts, self._missions, self._discovery = contexts, missions, discovery
        self._research, self._cases, self._drafts = research, cases, drafts
        self._store, self._settings = store, settings

    # ── the step runner ─────────────────────────────────────────────────────────────────────

    def _step(
        self,
        mission_id: str,
        kind: TaskKind,
        tool: str,
        work: Callable[[WorkflowMission, WorkflowTask], StepResult],
    ) -> Result:
        ticket = self.engine.begin_task(mission_id, kind)
        task = ticket.task
        base = {"mission_id": mission_id, "task_id": task.id}
        if ticket.cached:
            state = ticket.mission.state
            return {**task.output, **base, "ok": True, "cached": True, "state": state}
        self.engine.tool_event(task.id, tool, "started")
        try:
            result = work(ticket.mission, task)
        except StepError as exc:
            return self._failed(task, tool, exc)
        except Exception as exc:  # noqa: BLE001 - a crash must not leave a task "running"
            return self._failed(task, tool, StepError("internal", type(exc).__name__, True))
        self.engine.tool_event(task.id, tool, "completed", summary=result.summary)
        m = self.engine.complete_task(task.id, result.output, result.artifact_ids, result.summary)
        if result.wait_reason:
            m = self.engine.wait_for_input(mission_id, result.wait_reason)
        return {**result.output, **base, "ok": True, "cached": False, "state": m.state}

    def _failed(self, task: WorkflowTask, tool: str, exc: StepError) -> Result:
        self.engine.tool_event(task.id, tool, "completed", ok=False, summary=exc.kind)
        m = self.engine.fail_task(task.id, exc.kind, exc.message, exc.retryable)
        return {
            "ok": False,
            "error": exc.kind,
            "message": exc.message,
            "retryable": m.state == "NEEDS_RETRY",
            "mission_id": task.mission_id,
            "task_id": task.id,
            "state": m.state,
        }

    def _provider_calls(self, task: WorkflowTask, calls: list[CallRecord]) -> None:
        """Every provider call made for this step, as the receipt recorded it."""
        for i, c in enumerate(calls):
            self.engine.tool_event(
                task.id,
                c.endpoint,
                "completed",
                ok=c.ok,
                summary=f"{c.method} {c.endpoint}: {c.result_count} results ({c.mode})",
                key=i,
                data={
                    "provider": "crustdata",
                    "mode": c.mode,
                    "status_code": c.status_code,
                    "result_count": c.result_count,
                    "credits_used": c.credits_used,
                    "latency_ms": c.latency_ms,
                    "attempts": c.attempts,
                    "error_kind": c.error_kind,
                    "replay_source": c.replay_source,
                },
            )

    # ── intake and profile ──────────────────────────────────────────────────────────────────

    @guarded
    def create_mission(
        self, website_url: str, goal: str, brief: IntakeBrief | None = None
    ) -> Result:
        s = self._settings
        missing = self.fixture_problem(website_url)
        if missing:
            return {"ok": False, "error": "no_fixture", "message": missing}
        m = self.engine.create_mission(website_url, goal, s.run_mode, dict(s.provider_modes))

        def work(mission: WorkflowMission, task: WorkflowTask) -> StepResult:
            try:
                out = self._contexts.intake(website_url, goal, initiated_by=ACTOR, brief=brief)
            except UnsafeUrlError as exc:
                raise StepError("unsafe_url", exc.reason, False) from exc
            except IntakeFailed as exc:
                raise StepError("intake_failed", str(exc), True) from exc
            ctx = out.context
            self.engine.set_refs(mission.id, context_id=out.context_id)
            unsupported = [c.text for _, c in ctx.iter_claims() if c.status == "unsupported"]
            company = ctx.company_name.text if ctx.company_name else None
            return StepResult(
                {
                    "context_id": out.context_id,
                    "version": ctx.version,
                    "company": company,
                    "unsupported_claims": unsupported,
                    "clarification_questions": ctx.clarification_questions,
                    "unknowns": ctx.unknowns,
                    "readability": ctx.readability,
                    "usable": ctx.has_usable_facts(),
                    "your_statements": [
                        c.text for _, c in ctx.iter_claims() if c.kind == "user_provided"
                    ],
                },
                f"Read the site of {company or website_url} ({ctx.readability})",
                [out.context_id],
            )

        out = self._step(m.id, "profile_intake", "create_mission", work)
        return {**out, "mode": s.run_mode, "provider_modes": dict(s.provider_modes)}

    def fixture_problem(self, website_url: str) -> str | None:
        """In fixture mode a site with no recording can only fail, so say so before starting."""
        s = self._settings
        if s.provider_modes["web"] != "replay":
            return None
        root = Path(s.fixtures_dir) / "sites"
        try:
            host = check_url_static(normalize_seed_url(website_url))
        except UnsafeUrlError:
            return None  # the intake reports this with its own reason
        if host and (root / host).is_dir():
            return None
        known = ", ".join(sorted(p.name for p in root.iterdir() if p.is_dir()))
        return (
            f"Fixture mode has no recording of {host or website_url}. It only has: {known}. "
            "To read a real site, restart with scripts/office.sh (without --fixture)."
        )

    def _approval_target(self, m: WorkflowMission, gate: ApprovalGate) -> tuple[str, str]:
        """What is being approved comes from the records, never from the caller."""
        if gate == "business_profile":
            if not m.context_id:
                raise InvalidTransition("the mission has no business profile yet")
            ctx = self._contexts.get(m.context_id)
            name = ctx.company_name.text if ctx.company_name else m.website_url
            target = stable_id("ctx", m.context_id, ctx.version)
            return target, f"Review the business profile of {name} (version {ctx.version})"
        if gate == "icp_plan":
            if not m.gtm_mission_id:
                raise InvalidTransition("the mission has no ICP yet")
            plan = self._missions.get(m.gtm_mission_id)
            target = self._plan_hash(plan)
            return target, f"Review the ICP and up to {plan.estimated_credits} credits of search"
        if not m.draft_id:
            raise InvalidTransition("the mission has no draft yet")
        draft = self._drafts.get(m.draft_id)
        return draft.content_hash, (
            f"Review the draft to {draft.recipient_title} at {draft.account_name}. "
            "Approval records intent; nothing is sent."
        )

    @guarded
    def request_user_approval(self, mission_id: str, gate: ApprovalGate) -> Result:
        m = self.engine.mission(mission_id)
        target, summary = self._approval_target(m, gate)
        a = self.engine.request_approval(mission_id, gate, target, summary)
        return {
            "ok": True,
            "approval_id": a.id,
            "gate": a.gate,
            "status": a.status,
            "target_hash": a.target_hash,
            "summary": a.summary,
            "state": self.engine.mission(mission_id).state,
        }

    def _pending(self, mission_id: str, approval_id: str) -> Any:
        a = self.engine.approval(approval_id)
        if a.mission_id != mission_id:
            raise ApprovalMissing("that approval belongs to another mission")
        return a

    @guarded
    def approve_business_profile(
        self, mission_id: str, approval_id: str, acknowledge_unsupported: bool
    ) -> Result:
        a = self._pending(mission_id, approval_id)
        m = self.engine.mission(mission_id)
        target, _ = self._approval_target(m, "business_profile")
        if m.context_id is None or target != a.target_hash:
            raise ApprovalMissing("the profile changed after it was put up for approval")
        try:
            version = self._contexts.get(m.context_id).version
            self._contexts.approve(m.context_id, ACTOR, acknowledge_unsupported, version)
        except UnsupportedFactsRemain as exc:
            return {"ok": False, "error": "unsupported_facts", "unsupported": exc.texts}
        except EmptyProfile as exc:
            return {"ok": False, "error": "empty_profile", "message": str(exc)}
        except (VersionMismatch, ContextNotFound) as exc:
            return {"ok": False, "error": "profile_changed", "message": str(exc)}
        # An edit makes a new version; approval makes one too, so the bound hash stays the
        # version the human saw, not the frozen copy.
        self.engine.resolve_approval(a.id, "approved", HUMAN, a.target_hash)
        return {"ok": True, "state": self.engine.mission(mission_id).state}

    @guarded
    def edit_business_profile(self, mission_id: str, field: str, values: list[str]) -> Result:
        """Applies the user's answer or correction. A new version needs review again."""
        m = self.engine.mission(mission_id)
        if m.state != "PROFILE_REVIEW" or m.context_id is None:
            raise InvalidTransition(f"the profile can only change in PROFILE_REVIEW, not {m.state}")
        try:
            ctx = self._contexts.edit(m.context_id, {field: values})
        except InvalidEdit as exc:
            return {"ok": False, "error": "invalid_edit", "message": str(exc)}
        self.engine.expire_approvals(mission_id, "business_profile")
        return {"ok": True, "version": ctx.version, "state": m.state}

    @guarded
    def build_icp(self, mission_id: str) -> Result:
        def work(m: WorkflowMission, task: WorkflowTask) -> StepResult:
            if m.context_id is None:
                raise StepError("no_profile", "the mission has no business profile", False)
            try:
                ctx = self._contexts.get(m.context_id)
                lessons = self.lessons_for(ctx.domain, m.mode)
                gtm = self._missions.compile(
                    m.context_id,
                    initiated_by=ACTOR,
                    lessons=lessons_block(lessons),
                    favoured_signals=[
                        x["value"]
                        for x in lessons
                        if x.get("dimension") == "signal_type" and x.get("value")
                    ],
                )
            except ContextNotApproved as exc:
                raise StepError("context_not_approved", str(exc), False) from exc
            except MissionCompileFailed as exc:
                raise StepError("icp_failed", str(exc), True) from exc
            self.engine.set_refs(m.id, gtm_mission_id=gtm.id)
            plan = gtm.plan
            body = {
                "icp_query": plan.icp_query,
                "countries": plan.countries,
                "employee_ranges": plan.employee_ranges,
                "personas": [{"title": p.title, "why": p.why} for p in plan.personas],
                "signal_types": list(plan.signal_types),
                "max_accounts": plan.max_accounts,
                "assumptions": plan.assumptions,
                "open_questions": plan.open_questions,
                "estimated_credits": gtm.estimated_credits,
            }
            self.engine.publish_artifact(task.id, "icp", gtm.id, "ICP proposed", body)
            self._version_icp(m, gtm, "ICP Strategist", "First proposal from the approved profile")
            summary = f"ICP proposed with {len(plan.assumptions)} assumptions"
            return StepResult(body, summary, [gtm.id])

        return self._step(mission_id, "build_icp", "build_icp", work)

    @guarded
    def build_strategy(self, mission_id: str) -> Result:
        def work(m: WorkflowMission, task: WorkflowTask) -> StepResult:
            if m.context_id is None:
                raise StepError("no_profile", "the mission has no business profile", False)
            ctx = self._contexts.get(m.context_id)
            lessons = self.lessons_for(ctx.domain, m.mode)
            req = LlmRequest(
                task="strategy",
                replay_key=ctx.domain,
                system=STRATEGY_PROMPT,
                user=build_strategy_message(ctx) + lessons_block(lessons),
                schema=StrategyDraft,
                max_tokens=8000,
            )
            try:
                resp = self._llm.complete(req)
            except LlmError as exc:
                raise StepError("strategy_failed", str(exc), True) from exc
            known = [c.text for c in ctx.competitors if c.status != "unsupported"]
            proof = [c.text for c in ctx.proof_points if c.status == "supported"]
            body = label_strategy(resp.output, known, proof).model_dump(mode="json")
            body["lessons_used"] = [x["id"] for x in lessons]
            version = self._save_strategy(mission_id, body, "ICP Strategist", [], resp.mode)
            self.engine.publish_artifact(
                task.id, "strategy", f"{mission_id}.strategy.{version}", "Strategy drafted", {}
            )
            summary = f"Strategy version {version}: {body['gtm_motion']['motion']}"
            return StepResult({"version": version, "motion": body["gtm_motion"]["motion"]}, summary)

        return self._step(mission_id, "build_strategy", "build_strategy", work)

    def strategy_versions(self, mission_id: str) -> list[dict[str, Any]]:
        return self.engine.records("strategy", mission_id)

    def _save_strategy(
        self,
        mission_id: str,
        body: dict[str, Any],
        author: str,
        changes: list[str],
        mode: str,
        rolled_back_to: int | None = None,
    ) -> int:
        version = len(self.strategy_versions(mission_id)) + 1
        self.engine.save_record(
            "strategy",
            f"{mission_id}.strategy.{version}",
            mission_id,
            {
                "version": version,
                "status": "hypothesis",
                "author": author,
                "changes": changes,
                "mode": mode,
                "method": STRATEGY_PROMPT_VERSION,
                "rolled_back_to": rolled_back_to,
                "body": body,
            },
        )
        return version

    def strategy_version(self, mission_id: str) -> int | None:
        versions = self.strategy_versions(mission_id)
        return versions[-1]["version"] if versions else None

    def lessons_for(self, domain: str, mode: str) -> list[dict[str, Any]]:
        """Approved lessons for this seller, across missions. Fixture lessons stay in fixture."""
        wanted = teach_modes(mode)
        return [
            x
            for x in self.engine.all_records("lesson")
            if x["status"] == "approved" and x["domain"] == domain and x["mode"] in wanted
        ]

    def is_suppressed(self, mission_id: str, target_id: str) -> bool:
        return any(
            s["target_id"] == target_id for s in self.engine.records("suppression", mission_id)
        )

    def targets(self, mission_id: str) -> list[dict[str, Any]]:
        return self.engine.records("target", mission_id)

    def outreach(self, mission_id: str) -> list[dict[str, Any]]:
        return self.engine.records("outreach", mission_id)

    @guarded
    def add_target(self, mission_id: str, fields: dict[str, Any]) -> Result:
        """A recipient the user names. It is their statement, not a discovered fact."""
        self.engine.mission(mission_id)
        name = str(fields.get("name") or "").strip()
        audience = str(fields.get("audience") or "")
        if not name or audience not in AUDIENCES:
            return {"ok": False, "error": "invalid_target", "message": "name and audience needed"}
        rid = stable_id("tgt", mission_id, name, audience)
        record = {
            "id": rid,
            "name": name,
            "audience": audience,
            "notes": str(fields.get("notes") or ""),
            "source": "user",
        }
        self.engine.save_record("target", rid, mission_id, record)
        return {"ok": True, **record}

    @guarded
    def target_from_account(self, mission_id: str, account_id: int, audience: str) -> Result:
        """A researched, qualified account as an outreach target. Why it is worth reaching comes
        from the research run's own signals, so no one types it, and the learning loop can learn
        which signals lead to meetings. A rejected account stays out."""
        m = self.engine.mission(mission_id)
        if audience not in AUDIENCES:
            return {"ok": False, "error": "invalid_target", "message": "unknown audience"}
        if m.research_id is None:
            return {"ok": False, "error": "no_research", "message": "research the accounts first"}
        found = next(
            (
                a
                for a in self._research.get(m.research_id).accounts
                if a.account.provider_company_id == account_id
            ),
            None,
        )
        if found is None or not found.account.name:
            return {"ok": False, "error": "not_found", "message": f"account {account_id}"}
        if found.score.status != "qualified":
            message = f"the account is {found.score.status}"
            return {"ok": False, "error": "not_qualified", "message": message}
        active = [s for s in found.signals if s.status == "active"]
        rid = stable_id("tgt", mission_id, found.account.name, audience)
        record = {
            "id": rid,
            "name": found.account.name,
            "audience": audience,
            "notes": "",  # notes feed the writer; the why-now stays here, out of the message
            "source": "discovered",
            "account_id": account_id,
            "signal_types": sorted({s.type for s in active}),
            "why_now": [s.description for s in active],
            **_buyer(found.best_person),
        }
        self.engine.save_record("target", rid, mission_id, record)
        return {"ok": True, **record}

    @guarded
    def add_sample_targets(self, mission_id: str) -> Result:
        """Made-up targets for testing. Named SAMPLE so they can never pass for real ones."""
        for fields in SAMPLE_TARGETS:
            self.add_target(mission_id, fields)
        return {"ok": True, "targets": len(self.targets(mission_id))}

    @guarded
    def prepare_test_send(self, mission_id: str, outreach_id: str) -> Result:
        """Exactly what to send to the test inbox. The real recipient is never contacted."""
        record = self._outreach_record(mission_id, outreach_id)
        if record is None:
            return {"ok": False, "error": "not_found", "message": outreach_id}
        live = self._settings.outreach_mode == "live"
        target = self._target(mission_id, record["target_id"])
        buyer_email = str((target or {}).get("buyer_email") or "").strip()
        if live and not buyer_email:
            return {"ok": False, "error": "no_recipient", "message": "no email for this person"}
        if not live and not self.test_recipients:
            return {"ok": False, "error": "no_test_inbox", "message": "no test inbox is set"}
        if self.is_suppressed(mission_id, record["target_id"]):
            return {"ok": False, "error": "suppressed", "message": "this target opted out"}
        record = self._recheck(mission_id, record)
        if record["status"] not in ("verified", "approved"):
            return {"ok": False, "error": "not_verified", "message": "fix the findings first"}
        if live:  # UNVERIFIED: live sending has not been exercised against a real inbox
            return {
                "ok": True,
                "to": [buyer_email],
                "subject": record["subject"],
                "body": record["body"],
            }
        note = f"Written for {record['target_name']}, who was not contacted."
        if target and buyer_email:
            note = f"Demo: in live mode this goes to {target['buyer_name']} <{buyer_email}>."
        return {
            "ok": True,
            "to": [self.test_recipients[0]],
            "subject": f"[Trigger Point test] {record['subject']}",
            "body": f"{record['body']}\n\n---\nTrigger Point test. {note}",
        }

    def _target(self, mission_id: str, target_id: str) -> dict[str, Any] | None:
        return next((t for t in self.targets(mission_id) if t["id"] == target_id), None)

    @guarded
    def record_test_send(
        self, mission_id: str, outreach_id: str, to: str, message_id: str, thread_id: str
    ) -> Result:
        """Keeps the provider's ids. Sending a test does not approve anything."""
        record = self._outreach_record(mission_id, outreach_id)
        if record is None:
            return {"ok": False, "error": "not_found", "message": outreach_id}
        allowed = set(self.test_recipients)
        if self._settings.outreach_mode == "live":
            target = self._target(mission_id, record["target_id"]) or {}
            allowed = {str(target.get("buyer_email") or "").strip().casefold()} - {""}
        if to.strip().casefold() not in allowed:
            return {"ok": False, "error": "not_test_inbox", "message": "only the allowed inbox"}
        sends = [
            *record.get("test_sends", []),
            {
                "to": to,
                "message_id": message_id,
                "thread_id": thread_id,
                "sent_on": self.today().isoformat(),
            },
        ]
        updated = {**record, "test_sends": sends}
        if record.get("schedule", {}).get("state") in ("scheduled", "due"):
            updated["schedule"] = {**record["schedule"], "state": "sent"}
        self.engine.save_record("outreach", outreach_id, mission_id, updated)
        return {"ok": True, "test_sends": len(sends)}

    @guarded
    def record_test_meeting(self, mission_id: str, fields: dict[str, Any]) -> Result:
        """A real calendar event for a test. Its outcome is marked so it can never teach."""
        m = self.engine.mission(mission_id)
        rid = stable_id("mtg", mission_id, len(self.meetings(mission_id)), fields)
        self.engine.save_record(
            "meeting",
            rid,
            mission_id,
            {**fields, "id": rid, "mission_id": mission_id, "source": "google_calendar"},
        )
        return self.record_outcome(
            m.id,
            {
                "kind": "meeting_booked",
                "occurred_on": fields.get("held_on"),
                "account_name": fields.get("account_name"),
                "source": "google_calendar",
                "note": f"Test meeting: {fields.get('title')}",
            },
            mode="test",
        )

    def _approved_context(self, m: WorkflowMission) -> BusinessContext:
        ctx = self._contexts.get(m.context_id) if m.context_id else None
        if ctx is None or ctx.status != "approved":
            raise ApprovalMissing("approve the business profile first")
        return ctx

    @guarded
    def write_outreach(
        self, mission_id: str, target_id: str, follow_up_of: str | None = None
    ) -> Result:
        """One message for one target. A failed check gets one revision, then stays rejected."""
        m = self.engine.mission(mission_id)
        ctx = self._approved_context(m)
        target = next((t for t in self.targets(mission_id) if t["id"] == target_id), None)
        if target is None:
            return {"ok": False, "error": "not_found", "message": target_id}
        audience = AUDIENCES[target["audience"]]
        facts = approved_facts(ctx)
        lessons = self.lessons_for(ctx.domain, m.mode)
        testing = any(x.get("experiment") for x in lessons)
        variant = _variant(target_id) if testing else "none"
        used = [] if variant == "holdout" else lessons
        message = build_outreach_message(
            ctx, audience, target["name"], target["notes"]
        ) + lessons_block(used)
        parent = self._outreach_record(mission_id, follow_up_of) if follow_up_of else None
        if parent is not None:
            message += (
                f"\n<earlier_message>{html.escape(parent['body'], quote=False)}</earlier_message>"
            )
            message += "\nThis is a follow-up. Take a new angle. Do not repeat the earlier message."
        attempts = []
        wire = None
        findings = []
        mode = "replay"
        for attempt in (1, 2):
            req = LlmRequest(
                task="outreach",
                replay_key=f"{ctx.domain}__{target['audience']}",
                system=OUTREACH_PROMPT,
                user=message,
                schema=OutreachWire,
                max_tokens=4000,
            )
            try:
                resp = self._llm.complete(req)
            except LlmError as exc:
                return {"ok": False, "error": "outreach_failed", "message": str(exc)}
            wire, mode = resp.output, resp.mode
            findings = verify_outreach(wire, facts, target["name"], target["notes"])
            attempts.append(
                {"attempt": attempt, "findings": [f.model_dump(mode="json") for f in findings]}
            )
            if not findings:
                break
            problems = "; ".join(f.message for f in findings)
            message += f"\n<fix_these>{problems}</fix_these>"
        assert wire is not None  # noqa: S101 - the loop always runs
        rid = stable_id("otr", mission_id, target_id, len(self.outreach(mission_id)))
        record = {
            "id": rid,
            "target_id": target_id,
            "target_name": target["name"],
            "audience": target["audience"],
            "purpose": audience.purpose,
            "ask": audience.ask,
            "subject": wire.subject,
            "body": wire.body,
            "status": "rejected" if findings else "verified",
            "sending": "disabled",
            "content_hash": outreach_hash(target_id, wire.subject, wire.body),
            "attempts": attempts,
            "mode": mode,
            "prompt_version": OUTREACH_PROMPT_VERSION,
            "verifier": OUTREACH_VERSION,
            "variant": variant,
            "signal_types": target.get("signal_types", []),
            "account_id": target.get("account_id"),
            "lessons_used": [x["id"] for x in used],
            "strategy_version": self.strategy_version(mission_id),
            "step": (parent.get("step", 1) + 1) if parent else 1,
            "follow_up_of": follow_up_of,
        }
        self.engine.save_record("outreach", rid, mission_id, record)
        return {"ok": True, **record}

    def _outreach_record(self, mission_id: str, outreach_id: str) -> dict[str, Any] | None:
        return next((o for o in self.outreach(mission_id) if o["id"] == outreach_id), None)

    def _recheck(self, mission_id: str, record: dict[str, Any]) -> dict[str, Any]:
        """Rules tighten. A message is judged by today's rules at the moment it leaves."""
        if record["status"] not in ("verified", "approved"):
            return record
        ctx = self._approved_context(self.engine.mission(mission_id))
        target = next(t for t in self.targets(mission_id) if t["id"] == record["target_id"])
        wire = OutreachWire(subject=record["subject"], body=record["body"], claims=[])
        findings = verify_outreach(wire, approved_facts(ctx), target["name"], target["notes"])
        if not findings:
            return record
        updated = {
            **record,
            "status": "rejected",
            "attempts": [
                *record["attempts"],
                {"attempt": "recheck", "findings": [f.model_dump(mode="json") for f in findings]},
            ],
        }
        self.engine.save_record("outreach", record["id"], mission_id, updated)
        return updated

    @guarded
    def edit_outreach(self, mission_id: str, outreach_id: str, subject: str, body: str) -> Result:
        """A person's edit is checked like any other text, and any approval lapses."""
        record = self._outreach_record(mission_id, outreach_id)
        if record is None:
            return {"ok": False, "error": "not_found", "message": outreach_id}
        m = self.engine.mission(mission_id)
        ctx = self._approved_context(m)
        target = next(t for t in self.targets(mission_id) if t["id"] == record["target_id"])
        wire = OutreachWire(subject=subject, body=body, claims=[])
        findings = verify_outreach(wire, approved_facts(ctx), target["name"], target["notes"])
        updated = {
            **record,
            "subject": subject,
            "body": body,
            "status": "rejected" if findings else "verified",
            "content_hash": outreach_hash(record["target_id"], subject, body),
            "attempts": [
                *record["attempts"],
                {"attempt": "edit", "findings": [f.model_dump(mode="json") for f in findings]},
            ],
        }
        self.engine.save_record("outreach", outreach_id, mission_id, updated)
        return {"ok": True, **updated}

    @guarded
    def approve_outreach(self, mission_id: str, outreach_id: str, expected_hash: str) -> Result:
        """Records approval of this exact text. There is no path from here to sending."""
        record = self._outreach_record(mission_id, outreach_id)
        if record is None:
            return {"ok": False, "error": "not_found", "message": outreach_id}
        if record["content_hash"] != expected_hash:
            return {"ok": False, "error": "changed", "message": "the text changed after review"}
        record = self._recheck(mission_id, record)
        if record["status"] != "verified":
            return {"ok": False, "error": "not_verified", "message": "fix the findings first"}
        updated = {**record, "status": "approved"}
        self.engine.save_record("outreach", outreach_id, mission_id, updated)
        return {"ok": True, **updated}

    def _link(self, mission_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Traces an outcome to the message and strategy behind it, when the name matches."""
        name = str(fields.get("account_name") or "").casefold()
        sent = [
            o
            for o in self.outreach(mission_id)
            if o["target_name"].casefold() == name
            and (o.get("test_sends") or o.get("manual_sends"))
        ]
        if not sent:
            return {"strategy_version": self.strategy_version(mission_id)}
        return {
            "outreach_id": sent[-1]["id"],
            "audience": sent[-1]["audience"],
            "strategy_version": sent[-1].get("strategy_version"),
        }

    def outcomes(self, mission_id: str) -> list[Outcome]:
        return [Outcome.model_validate(o) for o in self.engine.records("outcome", mission_id)]

    @guarded
    def record_outcome(
        self, mission_id: str, fields: dict[str, Any], mode: str | None = None
    ) -> Result:
        """A fact about the real world. It carries the mission's mode, so fixture never teaches."""
        m = self.engine.mission(mission_id)
        rid = stable_id("out", mission_id, len(self.outcomes(mission_id)), fields)
        link = self._link(mission_id, fields)
        try:
            o = Outcome.model_validate(
                {
                    **link,
                    **fields,
                    "id": rid,
                    "mission_id": mission_id,
                    "mode": mode or outcome_mode(m.mode, fields),
                }
            )
        except ValidationError as exc:
            return {"ok": False, "error": "invalid_outcome", "message": exc.errors()[0]["msg"]}
        self.engine.save_record("outcome", rid, mission_id, o.model_dump(mode="json"))
        return {"ok": True, "id": rid}

    def meetings(self, mission_id: str) -> list[dict[str, Any]]:
        return self.engine.records("meeting", mission_id)

    @guarded
    def add_meeting(self, mission_id: str, fields: dict[str, Any]) -> Result:
        self.engine.mission(mission_id)
        rid = stable_id("mtg", mission_id, len(self.meetings(mission_id)), fields)
        record = {**fields, "id": rid, "mission_id": mission_id, "source": "manual"}
        self.engine.save_record("meeting", rid, mission_id, record)
        if fields.get("status") in ("missed", "cancelled"):
            return {"ok": True, "id": rid}  # nothing happened, so no outcome
        upcoming = str(fields.get("held_on") or "") > datetime.now(UTC).date().isoformat()
        return self.record_outcome(
            mission_id,
            {
                "kind": "meeting_booked" if upcoming else "meeting_held",
                "occurred_on": fields.get("held_on"),
                "account_name": fields.get("account_name"),
                "note": f"Meeting: {fields.get('title')}",
            },
        )

    def costs(self, mission_id: str) -> list[dict[str, Any]]:
        return self.engine.records("cost", mission_id)

    @guarded
    def add_cost(self, mission_id: str, fields: dict[str, Any]) -> Result:
        self.engine.mission(mission_id)
        rid = stable_id("cost", mission_id, len(self.costs(mission_id)), fields)
        self.engine.save_record("cost", rid, mission_id, {**fields, "id": rid})
        return {"ok": True, "id": rid}

    def proposals(self, mission_id: str) -> list[dict[str, Any]]:
        return self.engine.records("proposal", mission_id)

    @guarded
    def add_proposal(
        self,
        mission_id: str,
        change: str,
        evidence: str,
        outcome_ids: list[str],
        dimension: str | None = None,
        value: str | None = None,
    ) -> Result:
        self.engine.mission(mission_id)
        rid = stable_id("prop", mission_id, len(self.proposals(mission_id)), change)
        record = {
            "id": rid,
            "change": change,
            "evidence": evidence,
            "outcome_ids": outcome_ids,
            "dimension": dimension,  # what was compared, e.g. signal_type, so it can be acted on
            "value": value,
            "status": "proposed",
        }
        self.engine.save_record("proposal", rid, mission_id, record)
        return {"ok": True, **record}

    @guarded
    def decide_proposal(self, mission_id: str, proposal_id: str, decision: str) -> Result:
        """A person's decision. Approval versions the strategy; nothing changes silently."""
        found = next((p for p in self.proposals(mission_id) if p["id"] == proposal_id), None)
        if found is None:
            return {"ok": False, "error": "not_found", "message": proposal_id}
        if found["status"] != "proposed":
            return {"ok": False, "error": "already_decided", "message": found["status"]}
        self.engine.save_record("proposal", proposal_id, mission_id, {**found, "status": decision})
        if decision != "approved":
            return {"ok": True, "status": decision}
        out = self.version_strategy(mission_id, [found["change"]])
        return {**out, "status": decision} if out["ok"] else out

    def version_strategy(
        self, mission_id: str, changes: list[str], extra: dict[str, Any] | None = None
    ) -> Result:
        """One approved decision becomes one new strategy version."""
        versions = self.strategy_versions(mission_id)
        if not versions:
            return {"ok": False, "error": "no_strategy", "message": "nothing to version"}
        last = versions[-1]
        body = {**last["body"], **(extra or {})}
        body["guidance"] = [*last["body"].get("guidance", []), *changes]
        return {
            "ok": True,
            "version": self._save_strategy(mission_id, body, "user", changes, last["mode"]),
        }

    @guarded
    def rollback_strategy(self, mission_id: str, version: int) -> Result:
        versions = self.strategy_versions(mission_id)
        target = next((v for v in versions if v["version"] == version), None)
        if target is None:
            return {"ok": False, "error": "not_found", "message": f"no version {version}"}
        new = self._save_strategy(
            mission_id,
            target["body"],
            "user",
            [f"Rolled back to version {version}"],
            target["mode"],
            rolled_back_to=version,
        )
        return {"ok": True, "version": new}

    def _plan_hash(self, gtm: Mission) -> str:
        return stable_id("plan", gtm.id, gtm.plan.model_dump_json(), gtm.search_request)

    def _version_icp(self, m: WorkflowMission, gtm: Mission, author: str, why: str) -> IcpVersion:
        versions = self.engine.icp_versions(m.id)
        previous = versions[-1] if versions else None
        icp = build_icp(
            gtm.plan,
            m.id,
            gtm.id,
            (previous.version + 1) if previous else 1,
            author,
            why,
            previous,
            self._plan_hash(gtm),
        )
        return self.engine.record_icp(
            icp.model_copy(update={"estimated_credits": gtm.estimated_credits})
        )

    @guarded
    def edit_icp(self, mission_id: str, changes: dict[str, object], rationale: str) -> Result:
        """A human revision while the plan is under review. Discovery has not spent anything."""
        m = self.engine.mission(mission_id)
        if m.state != "ICP_READY" or m.gtm_mission_id is None:
            raise InvalidTransition(f"the ICP can only be edited in ICP_READY, not {m.state}")
        unknown = set(changes) - ICP_EDITABLE
        if unknown:
            return {"ok": False, "error": "invalid_edit", "message": f"not editable: {unknown}"}
        gtm = self._missions.revise(m.gtm_mission_id, changes)
        self.engine.expire_approvals(mission_id, "icp_plan")
        icp = self._version_icp(m, gtm, "user", rationale)
        return {"ok": True, "version": icp.version, "changes": icp.changes}

    @guarded
    def approve_icp_plan(self, mission_id: str, approval_id: str) -> Result:
        a = self._pending(mission_id, approval_id)
        m = self.engine.mission(mission_id)
        target, _ = self._approval_target(m, "icp_plan")
        if m.gtm_mission_id is None or target != a.target_hash:
            raise ApprovalMissing("the plan changed after it was put up for approval")
        self._missions.approve(m.gtm_mission_id)
        self.engine.resolve_approval(a.id, "approved", HUMAN, a.target_hash)
        self.engine.approve_icp(mission_id, a.target_hash)
        return {"ok": True, "state": self.engine.mission(mission_id).state}

    # ── research ────────────────────────────────────────────────────────────────────────────

    @guarded
    def discover_accounts(self, mission_id: str) -> Result:
        def work(m: WorkflowMission, task: WorkflowTask) -> StepResult:
            if m.gtm_mission_id is None:
                raise StepError("no_plan", "the mission has no ICP plan", False)
            try:
                run = self._discovery.run(m.gtm_mission_id, initiated_by=ACTOR)
            except DiscoveryFailed as exc:
                failed = self._store.get_discovery(exc.discovery_id)
                self._provider_calls(task, failed.calls if failed else [])
                raise _provider_error(str(exc)) from exc
            self._provider_calls(task, run.calls)
            self.engine.set_refs(m.id, discovery_id=run.id)
            output = {
                "accounts": len(run.accounts),
                "names": [a.name for a in run.accounts],
                "rejected": [r.model_dump(mode="json") for r in run.rejected],
                "relaxations": run.relaxations,
                "credits": run.credits,
                "mode": run.mode,
            }
            summary = f"Found {len(run.accounts)} candidate accounts ({run.mode})"
            wait = None if run.accounts else "Discovery found no accounts for this ICP"
            return StepResult(output, summary, [run.id], wait)

        return self._step(mission_id, "discover_accounts", "discover_accounts", work)

    def _board(self, run: ResearchRun) -> list[dict[str, Any]]:
        return [
            {
                "account_id": a.account.provider_company_id,
                "name": a.account.name,
                "status": a.score.status,
                "tier": a.score.tier,
                "total": a.score.total,
                "rejections": a.score.rejections,
                "active_signals": [s.description for s in a.signals if s.status == "active"],
                "buyer_title": a.best_person.person.current_title if a.best_person else None,
            }
            for a in run.accounts
        ]

    def _add_evidence(self, task: WorkflowTask, run: ResearchRun) -> int:
        records = [_record(e, a.account.name) for a in run.accounts for e in a.evidence]
        return self.engine.add_evidence(task.id, records)

    @guarded
    def research_account_signals(self, mission_id: str) -> Result:
        def work(m: WorkflowMission, task: WorkflowTask) -> StepResult:
            if m.discovery_id is None:
                raise StepError("no_discovery", "the mission has no accounts", False)
            try:
                run = self._research.run_signals(m.discovery_id, initiated_by=ACTOR)
            except ResearchFailed as exc:
                failed = self._store.get_research(exc.research_id)
                self._provider_calls(task, failed.calls if failed else [])
                raise _provider_error(str(exc)) from exc
            self._provider_calls(task, run.calls)
            self.engine.set_refs(m.id, research_id=run.id)
            added = self._add_evidence(task, run)
            signals = sum(len(a.signals) for a in run.accounts)
            output = {
                "research_id": run.id,
                "board": self._board(run),
                "notes": run.notes,
                "credits": run.credits,
                "mode": run.mode,
            }
            return StepResult(output, f"{signals} signals, {added} evidence records", [run.id])

        return self._step(mission_id, "research_signals", "research_account_signals", work)

    @guarded
    def map_buying_committee(self, mission_id: str) -> Result:
        def work(m: WorkflowMission, task: WorkflowTask) -> StepResult:
            if m.research_id is None:
                raise StepError("no_research", "the mission has no research run", False)
            known = len(self._research.get(m.research_id).calls)
            try:
                run = self._research.run_people(m.research_id)
            except ResearchFailed as exc:
                failed = self._store.get_research(exc.research_id)
                self._provider_calls(task, failed.calls[known:] if failed else [])
                raise _provider_error(str(exc)) from exc
            self._provider_calls(task, run.calls[known:])
            self._add_evidence(task, run)
            found = sum(1 for a in run.accounts if a.best_person)
            output = {
                "board": self._board(run),
                "buyers_found": found,
                "notes": run.notes,
                "credits": run.credits,
                "mode": run.mode,
            }
            return StepResult(output, f"Verified buyers at {found} accounts", [run.id])

        return self._step(mission_id, "map_committee", "map_buying_committee", work)

    # ── audit, score, draft, gate ───────────────────────────────────────────────────────────

    def _audited(self, run: ResearchRun, ar: AccountResearch) -> list[EvidenceRecord]:
        now = datetime.now(UTC)
        people = {str(ar.best_person.person.provider_person_id)} if ar.best_person else set()
        records = []
        for e in ar.evidence:
            cid = str(ar.account.provider_company_id)
            check = audit_evidence(e, cid, run.reference_date, now, people)
            r = _record(e, ar.account.name)
            r.verification_status, r.verification_reasons = check.status, check.reasons
            records.append(r)
        return records

    @guarded
    def verify_evidence(self, mission_id: str) -> Result:
        def work(m: WorkflowMission, task: WorkflowTask) -> StepResult:
            if m.research_id is None:
                raise StepError("no_research", "the mission has no research run", False)
            run = self._research.get(m.research_id)
            records = [r for ar in run.accounts for r in self._audited(run, ar)]
            self.engine.add_evidence(task.id, records)
            self.engine.record_verification(task.id, records)
            counts: dict[str, int] = {}
            for r in records:
                counts[r.verification_status] = counts.get(r.verification_status, 0) + 1
            failures = [
                {
                    "evidence_id": r.id,
                    "account": r.account,
                    "status": r.verification_status,
                    "reasons": r.verification_reasons,
                }
                for r in records
                if r.verification_status not in ("verified", "user_provided")
            ]
            output = {"total": len(records), "counts": counts, "failures": failures}
            verified = counts.get("verified", 0)
            return StepResult(output, f"{verified} of {len(records)} evidence records verified")

        return self._step(mission_id, "verify_evidence", "verify_evidence", work)

    def _case_body(self, case: AccountCase, statuses: dict[str, str]) -> dict[str, Any]:
        return {
            "account_id": case.account_id,
            "account_name": case.account_name,
            "account_domain": case.account_domain,
            "mode": case.mode,
            "score": case.score.model_dump(mode="json"),
            "why_account": _items(case.why_account),
            "why_person": _items(case.why_person),
            "why_now": _items(case.why_now),
            "why_us": _items(case.why_us),
            "coverage_gaps": case.coverage_gaps,
            "warm_path": case.warm_path,
            "route": case.recommended_route,
            "route_reason": case.route_reason,
            "evidence_ids": [e.id for e in case.evidence],
            "evidence_status": statuses,
        }

    def _case_checks(self, case: AccountCase, run: ResearchRun) -> dict[str, EvidenceCheck]:
        ar = next(a for a in run.accounts if a.account.provider_company_id == case.account_id)
        people = {str(ar.best_person.person.provider_person_id)} if ar.best_person else set()
        now = datetime.now(UTC)
        return {
            e.id: audit_evidence(e, str(case.account_id), run.reference_date, now, people)
            for e in case.evidence
        }

    @guarded
    def score_account(self, mission_id: str, account_id: int | None) -> Result:
        def work(m: WorkflowMission, task: WorkflowTask) -> StepResult:
            if m.research_id is None:
                raise StepError("no_research", "the mission has no research run", False)
            run = self._research.get(m.research_id)
            for ar in run.accounts:
                cid = ar.account.provider_company_id
                if ar.score.status != "qualified" or account_id not in (None, cid):
                    continue
                case = self._cases.get_or_build(run.id, cid)
                checks = self._case_checks(case, run)
                if case.recommended_route != "cold_email" or not any(
                    e in checks and checks[e].status == "verified" for e in case.hook_evidence_ids
                ):
                    continue
                return self._selected(m, task, case, checks, run)
            return StepResult(
                {"selected": None},
                "No account has a verified hook and a contactable buyer",
                wait_reason="No qualified account has audited evidence and a verified buyer",
            )

        return self._step(mission_id, "score_account", "score_account", work)

    def _selected(
        self,
        m: WorkflowMission,
        task: WorkflowTask,
        case: AccountCase,
        checks: dict[str, EvidenceCheck],
        run: ResearchRun,
    ) -> StepResult:
        self.engine.set_refs(m.id, selected_account_id=case.account_id)
        ar = next(a for a in run.accounts if a.account.provider_company_id == case.account_id)
        records = [_record(e, ar.account.name) for e in case.evidence]
        for r in records:
            r.verification_status = checks[r.id].status
            r.verification_reasons = checks[r.id].reasons
        self.engine.add_evidence(task.id, records)
        statuses: dict[str, str] = {eid: c.status for eid, c in checks.items()}
        body = self._case_body(case, statuses)
        recipient = case.recipient.person if case.recipient else None
        body["recipient"] = (
            {"name": recipient.name, "title": recipient.current_title} if recipient else None
        )
        self.engine.publish_artifact(
            task.id, "case_file", case.id, f"Case file for {case.account_name}", body
        )
        output = {
            "selected": {"account_id": case.account_id, "name": case.account_name},
            "score": case.score.model_dump(mode="json"),
        }
        summary = f"{case.account_name} scored {case.score.total} ({case.score.version})"
        return StepResult(output, summary, [case.id])

    @guarded
    def draft_campaign(self, mission_id: str) -> Result:
        def work(m: WorkflowMission, task: WorkflowTask) -> StepResult:
            if m.research_id is None or m.selected_account_id is None:
                raise StepError("no_account", "no account was selected", False)
            try:
                d = self._drafts.create(m.research_id, m.selected_account_id, initiated_by=ACTOR)
            except (CaseNotFound, DraftNotAllowed) as exc:
                raise StepError("not_contactable", str(exc), False) from exc
            except DraftFailed as exc:
                raise StepError("draft_failed", str(exc), True) from exc
            self.engine.set_refs(m.id, draft_id=d.id)
            self._publish_draft(task, d)
            if d.status != "verified":
                codes = [f.code for a in d.verifier_log for f in a.findings]
                raise StepError("draft_rejected", f"verifier: {', '.join(codes)}", True)
            output = {
                "draft_id": d.id,
                "status": d.status,
                "sending": d.sending,
                "subject": d.subject,
                "body": d.body,
                "content_hash": d.content_hash,
                "verifier_attempts": len(d.verifier_log),
            }
            return StepResult(output, f"Draft verified for {d.account_name}", [d.id])

        return self._step(mission_id, "draft_campaign", "draft_campaign", work)

    def _publish_draft(self, task: WorkflowTask, d: CampaignDraft) -> None:
        self.engine.publish_artifact(
            task.id,
            "campaign_draft",
            d.id,
            f"Draft for {d.account_name} ({d.status})",
            {
                "account_name": d.account_name,
                "recipient_name": d.recipient_name,
                "recipient_title": d.recipient_title,
                "channel": d.channel,
                "subject": d.subject,
                "body": d.body,
                "status": d.status,
                "sending": d.sending,
                "content_hash": d.content_hash,
                "hook_evidence_id": d.hook_evidence_id,
                "verifier_log": [v.model_dump(mode="json") for v in d.verifier_log],
            },
        )

    @guarded
    def run_quality_gate(self, mission_id: str) -> Result:
        def work(m: WorkflowMission, task: WorkflowTask) -> StepResult:
            if m.draft_id is None or m.research_id is None or m.selected_account_id is None:
                raise StepError("no_draft", "the mission has no draft", False)
            draft = self._drafts.get(m.draft_id)
            run = self._research.get(m.research_id)
            case = self._cases.get_or_build(m.research_id, m.selected_account_id)
            checks = self._case_checks(case, run)
            statuses: dict[str, str] = {eid: c.status for eid, c in checks.items()}
            result = quality_gate(draft, case, statuses, self._store.list_drafts())
            if not result.passed:
                codes = ", ".join(f.code for f in result.findings)
                raise StepError("quality_gate_failed", codes, False)
            output = {"passed": True, "findings": [], "version": result.version}
            return StepResult(output, "Quality gate passed")

        return self._step(mission_id, "quality_gate", "run_quality_gate", work)

    @guarded
    def approve_campaign_draft(
        self, mission_id: str, approval_id: str, expected_hash: str
    ) -> Result:
        a = self._pending(mission_id, approval_id)
        m = self.engine.mission(mission_id)
        if m.draft_id is None:
            raise ApprovalMissing("the mission has no draft")
        if expected_hash != a.target_hash:
            raise ApprovalMissing("the draft changed after it was put up for approval")
        try:
            self._drafts.approve(m.draft_id, expected_hash, HUMAN)
        except DraftStateError as exc:
            return {"ok": False, "error": "not_approvable", "message": str(exc)}
        self.engine.resolve_approval(a.id, "approved", HUMAN, expected_hash)
        state = self.engine.mission(mission_id).state
        return {"ok": True, "state": state, "sent": False}

    @guarded
    def reject_approval(self, mission_id: str, approval_id: str, reason: str) -> Result:
        a = self._pending(mission_id, approval_id)
        self.engine.resolve_approval(a.id, "rejected", HUMAN, a.target_hash, reason)
        return {"ok": True, "state": self.engine.mission(mission_id).state}

    @guarded
    def cancel_mission(self, mission_id: str, reason: str) -> Result:
        return {"ok": True, "state": self.engine.cancel_mission(mission_id, reason).state}

    # ── reads ───────────────────────────────────────────────────────────────────────────────

    @guarded
    def status(self, mission_id: str) -> Result:
        m = self.engine.mission(mission_id)
        events = self.engine.events(mission_id)
        approvals = [a.model_dump(mode="json") for a in self.engine.approvals(mission_id)]
        return {
            "ok": True,
            **m.model_dump(mode="json"),
            "mission_id": m.id,
            "tasks": [
                t.model_dump(mode="json", exclude={"output"}) for t in self.engine.tasks(mission_id)
            ],
            "approvals": approvals,
            "pending_approvals": [a for a in approvals if a["status"] == "pending"],
            "last_seq": events[-1].seq if events else 0,
        }

    @guarded
    def task_details(self, task_id: str) -> Result:
        task = self.engine.task(task_id)
        events = [e for e in self.engine.events(task.mission_id) if e.task_id == task_id]
        return {
            "ok": True,
            **task.model_dump(mode="json"),
            "events": [
                {
                    "seq": e.seq,
                    "type": e.event_type,
                    "summary": e.summary,
                    "at": e.occurred_at.isoformat(),
                }
                for e in events
            ],
            "evidence_ids": [
                eid for e in events if e.event_type == "evidence.created" for eid in e.artifact_ids
            ],
        }
