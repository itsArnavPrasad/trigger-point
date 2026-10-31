"""The mission state machine. Deterministic code decides every transition; a model or a hook
can ask for one, never force it. State and its events commit together, then events are offered
to the sink: a failed delivery leaves them queued and never touches the mission."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol

from trigger_point.workflow.icp import IcpVersion
from trigger_point.workflow.models import (
    GATE_STATES,
    MAX_ATTEMPTS,
    SPECS,
    TASK_LEASE_SECONDS,
    TASK_PLAN,
    TERMINAL,
    ApprovalGate,
    EventStatus,
    EventType,
    EvidenceRecord,
    MissionState,
    Role,
    TaskError,
    TaskKind,
    WorkflowApproval,
    WorkflowEvent,
    WorkflowMission,
    WorkflowTask,
    safe_text,
    stable_id,
)
from trigger_point.workflow.store import Tx, WorkflowStore

log = logging.getLogger(__name__)
FLUSH_BATCH = 100


class MissionNotFound(LookupError):
    pass


class TaskNotFound(LookupError):
    pass


class InvalidTransition(RuntimeError):
    pass


class TaskBusy(RuntimeError):
    pass


class ApprovalMissing(RuntimeError):
    pass


class EventSink(Protocol):
    def deliver(self, events: list[WorkflowEvent]) -> bool: ...


@dataclass(frozen=True)
class TaskTicket:
    task: WorkflowTask
    mission: WorkflowMission
    cached: bool = False


def _now() -> datetime:
    return datetime.now(UTC)


def _request_key(website_url: str, goal: str) -> str:
    return stable_id("req", website_url.strip().lower().rstrip("/"), goal.strip())


def _agent_id(mission_id: str, role: str) -> str:
    return f"{mission_id}.{role}"


class WorkflowEngine:
    def __init__(
        self,
        store: WorkflowStore,
        sink: EventSink | None = None,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._store, self._sink, self._clock = store, sink, clock

    # ── events ──────────────────────────────────────────────────────────────────────────────

    def _emit(
        self,
        tx: Tx,
        mission_id: str,
        type_: EventType,
        summary: str,
        *key: object,
        task: WorkflowTask | None = None,
        role: Role | None = None,
        status: EventStatus = "info",
        artifact_ids: list[str] | None = None,
        correlation_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        """The id comes from what the event is (mission, type, task, attempt, key), so saying
        the same thing twice is one event."""
        attempt = task.attempt if task else 0
        event_id = stable_id("evt", mission_id, type_, task.id if task else "", attempt, *key)
        if tx.has_event(event_id):
            return
        who = task.role if task else role
        now = self._clock()
        tx.add_event(
            WorkflowEvent(
                event_id=event_id,
                seq=tx.next_seq(mission_id),
                event_type=type_,
                occurred_at=now,
                recorded_at=now,
                mission_id=mission_id,
                task_id=task.id if task else None,
                agent_id=_agent_id(mission_id, who) if who else None,
                role=who,
                status=status,
                summary=safe_text(summary),
                artifact_ids=artifact_ids or [],
                correlation_id=correlation_id or (task.id if task else mission_id),
                data=data or {},
            )
        )

    def flush(self) -> None:
        """Offer queued events to the sink, oldest first. Telemetry never fails a mission."""
        if self._sink is None:
            return
        try:
            with self._store.view() as v:
                pending = v.undelivered(FLUSH_BATCH)
            while pending:
                if not self._sink.deliver(pending):
                    return
                with self._store.tx() as tx:
                    tx.mark_delivered([e.event_id for e in pending], self._clock())
                with self._store.view() as v:
                    pending = v.undelivered(FLUSH_BATCH)
        except Exception as exc:  # noqa: BLE001 - see docstring
            log.warning("event delivery failed: %s", type(exc).__name__)

    # ── reads ───────────────────────────────────────────────────────────────────────────────

    def mission(self, mission_id: str) -> WorkflowMission:
        with self._store.view() as v:
            m = v.mission(mission_id)
        if m is None:
            raise MissionNotFound(mission_id)
        return m

    def missions(self, limit: int = 20) -> list[WorkflowMission]:
        with self._store.view() as v:
            return v.missions(limit)

    def task(self, task_id: str) -> WorkflowTask:
        with self._store.view() as v:
            t = v.task(task_id)
        if t is None:
            raise TaskNotFound(task_id)
        return t

    def tasks(self, mission_id: str) -> list[WorkflowTask]:
        with self._store.view() as v:
            return v.tasks(mission_id)

    def events(self, mission_id: str) -> list[WorkflowEvent]:
        with self._store.view() as v:
            return v.events(mission_id)

    def approval(self, approval_id: str) -> WorkflowApproval:
        with self._store.view() as v:
            a = v.approval(approval_id)
        if a is None:
            raise ApprovalMissing(f"no approval {approval_id}")
        return a

    def approvals(self, mission_id: str) -> list[WorkflowApproval]:
        with self._store.view() as v:
            return v.approvals(mission_id)

    def records(self, kind: str, mission_id: str) -> list[dict[str, Any]]:
        with self._store.view() as v:
            return [json.loads(body) for body in v.records(kind, mission_id)]

    def save_record(self, kind: str, record_id: str, mission_id: str, body: dict[str, Any]) -> None:
        with self._store.tx() as tx:
            tx.save_record(kind, record_id, mission_id, json.dumps(body, default=str))

    def icp_versions(self, mission_id: str) -> list[IcpVersion]:
        with self._store.view() as v:
            return v.icp_versions(mission_id)

    def record_icp(self, icp: IcpVersion) -> IcpVersion:
        """Saves a new version, supersedes the one before it, and says so in the log."""
        stamped = icp.model_copy(update={"created_at": self._clock()})
        with self._store.tx() as tx:
            for old in tx.icp_versions(icp.mission_id):
                if old.status != "superseded":
                    tx.save_icp(old.model_copy(update={"status": "superseded"}))
            tx.save_icp(stamped)
            self._emit(
                tx,
                icp.mission_id,
                "strategy.versioned",
                f"ICP version {icp.version}: {icp.rationale}",
                icp.version,
                role="icp-strategist",
                data={"version": icp.version, "changes": icp.changes, "author": icp.author},
            )
        return stamped

    def expire_approvals(self, mission_id: str, gate: ApprovalGate) -> None:
        """The content under review changed: what was put up can no longer be approved."""
        with self._store.tx() as tx:
            for a in tx.approvals(mission_id):
                if a.gate == gate and a.status == "pending":
                    a.status, a.decided_at = "expired", self._clock()
                    tx.save_approval(a)

    def approve_icp(self, mission_id: str, target_hash: str) -> None:
        with self._store.tx() as tx:
            for icp in tx.icp_versions(mission_id):
                if icp.target_hash == target_hash:
                    tx.save_icp(icp.model_copy(update={"status": "approved"}))

    def evidence(self, mission_id: str) -> list[EvidenceRecord]:
        with self._store.view() as v:
            return v.evidence(mission_id)

    # ── mission ─────────────────────────────────────────────────────────────────────────────

    def create_mission(
        self, website_url: str, goal: str, mode: str, provider_modes: dict[str, str]
    ) -> WorkflowMission:
        key = _request_key(website_url, goal)
        now = self._clock()
        with self._store.tx() as tx:
            existing = tx.open_mission(key)
            if existing is not None:
                return existing
            m = WorkflowMission(
                id=f"wm_{uuid.uuid4().hex[:16]}",
                website_url=website_url,
                goal=goal,
                mode=mode,
                provider_modes=provider_modes,
                created_at=now,
                updated_at=now,
            )
            tx.save_mission(m, request_key=key)
            self._emit(
                tx,
                m.id,
                "mission.created",
                f"Mission received for {website_url} ({mode} mode)",
                role="mission-director",
                status="running",
                data={
                    "website_url": website_url,
                    "goal": safe_text(goal, 400),
                    "mode": mode,
                    "provider_modes": provider_modes,
                    "state": m.state,
                },
            )
            for position, spec in enumerate(TASK_PLAN):
                task = WorkflowTask(
                    id=f"{m.id}.{spec.kind}",
                    mission_id=m.id,
                    kind=spec.kind,
                    role=spec.role,
                    title=spec.title,
                    position=position,
                )
                tx.save_task(task)
                self._emit(
                    tx,
                    m.id,
                    "task.queued",
                    spec.title,
                    task=task,
                    status="queued",
                    data={"kind": spec.kind, "title": spec.title, "position": position},
                )
        self.flush()
        return m

    def _set_state(self, tx: Tx, m: WorkflowMission, state: MissionState) -> None:
        previous = m.state
        m.state, m.updated_at = state, self._clock()
        tx.save_mission(m)
        self._emit(
            tx,
            m.id,
            "mission.updated",
            f"Mission moved from {previous} to {state}",
            previous,
            state,
            len(tx.events(m.id)),
            role="mission-director",
            data={"from": previous, "to": state, "resume_state": m.resume_state},
        )

    def set_refs(self, mission_id: str, **refs: object) -> WorkflowMission:
        """Links a mission to the stage records it produced."""
        with self._store.tx() as tx:
            m = self._require(tx, mission_id)
            m = m.model_copy(update={**refs, "updated_at": self._clock()})
            tx.save_mission(m)
        return m

    def wait_for_input(self, mission_id: str, reason: str) -> WorkflowMission:
        with self._store.tx() as tx:
            m = self._require(tx, mission_id)
            self._to_waiting(tx, m, reason)
        self.flush()
        return m

    def _to_waiting(self, tx: Tx, m: WorkflowMission, reason: str) -> None:
        m.resume_state, m.wait_reason = m.state, safe_text(reason, 400)
        self._set_state(tx, m, "WAITING_FOR_INPUT")
        self._emit(
            tx,
            m.id,
            "mission.waiting",
            reason,
            len(tx.events(m.id)),
            role="mission-director",
            status="waiting_approval",
            data={"reason": m.wait_reason, "resume_state": m.resume_state},
        )

    def cancel_mission(self, mission_id: str, reason: str) -> WorkflowMission:
        with self._store.tx() as tx:
            m = self._require(tx, mission_id)
            if m.state in TERMINAL:
                raise InvalidTransition(f"mission is already {m.state}")
            self._close_open_work(tx, m)
            self._set_state(tx, m, "CANCELLED")
            self._emit(
                tx,
                m.id,
                "mission.cancelled",
                reason,
                role="mission-director",
                status="cancelled",
            )
        self.flush()
        return m

    def _close_open_work(self, tx: Tx, m: WorkflowMission) -> None:
        now = self._clock()
        for t in tx.tasks(m.id):
            if t.status in ("queued", "running", "waiting_approval"):
                t.status, t.finished_at = "cancelled", now
                tx.save_task(t)
        for a in tx.approvals(m.id):
            if a.status == "pending":
                a.status, a.decided_at = "expired", now
                tx.save_approval(a)

    def _require(self, tx: Tx, mission_id: str) -> WorkflowMission:
        m = tx.mission(mission_id)
        if m is None:
            raise MissionNotFound(mission_id)
        return m

    # ── tasks ───────────────────────────────────────────────────────────────────────────────

    def begin_task(self, mission_id: str, kind: TaskKind) -> TaskTicket:
        """Claim a task. A finished one comes back cached, so calling a tool twice never repeats
        the work or the spend; a running one is refused until its lease runs out."""
        spec = SPECS[kind]
        now = self._clock()
        with self._store.tx() as tx:
            m = self._require(tx, mission_id)
            task = tx.task(f"{mission_id}.{kind}")
            if task is None:
                raise TaskNotFound(f"{mission_id}.{kind}")
            if task.status == "succeeded":
                return TaskTicket(task, m, cached=True)
            if m.state in TERMINAL or m.state == "WAITING_FOR_INPUT":
                raise InvalidTransition(f"mission is {m.state}: {m.wait_reason or m.failure or ''}")
            state = m.resume_state if m.state == "NEEDS_RETRY" else m.state
            if state != spec.from_state:
                raise InvalidTransition(f"{kind} needs {spec.from_state}, mission is {state}")
            if task.status == "running" and task.started_at is not None:
                expires = task.started_at + timedelta(seconds=TASK_LEASE_SECONDS)
                if now < expires:
                    raise TaskBusy(f"{task.id} is already running (attempt {task.attempt})")
            if spec.gate and not any(
                a.gate == spec.gate and a.status == "approved" for a in tx.approvals(mission_id)
            ):
                raise ApprovalMissing(f"{kind} needs an approved {spec.gate}")
            if spec.after:
                earlier = tx.task(f"{mission_id}.{spec.after}")
                if earlier is None or earlier.status != "succeeded":
                    raise InvalidTransition(f"{kind} needs {spec.after} first")
            if m.state == "NEEDS_RETRY" and state is not None:
                m.resume_state = None
                self._set_state(tx, m, state)
            task.status, task.started_at, task.finished_at = "running", now, None
            task.attempt += 1
            task.error = None
            tx.save_task(task)
            if task.attempt > 1:
                self._emit(
                    tx,
                    m.id,
                    "task.retrying",
                    f"{spec.title}: attempt {task.attempt}",
                    task=task,
                    status="running",
                    data={"attempt": task.attempt},
                )
            self._emit(
                tx,
                m.id,
                "task.started",
                f"{spec.title} (attempt {task.attempt})",
                task=task,
                status="running",
                data={"kind": kind, "attempt": task.attempt},
            )
        self.flush()
        return TaskTicket(task, m)

    def complete_task(
        self,
        task_id: str,
        output: dict[str, Any],
        artifact_ids: list[str] | None = None,
        summary: str | None = None,
    ) -> WorkflowMission:
        with self._store.tx() as tx:
            task = self._running(tx, task_id)
            m = self._require(tx, task.mission_id)
            spec = SPECS[task.kind]
            task.status, task.finished_at = "succeeded", self._clock()
            task.output, task.artifact_ids = output, artifact_ids or []
            tx.save_task(task)
            self._emit(
                tx,
                m.id,
                "task.completed",
                summary or spec.title,
                task=task,
                status="succeeded",
                artifact_ids=task.artifact_ids,
                data={"output": output},
            )
            if spec.to_state is not None:
                self._set_state(tx, m, spec.to_state)
        self.flush()
        return m

    def fail_task(
        self, task_id: str, kind: str, message: str, retryable: bool, summary: str | None = None
    ) -> WorkflowMission:
        with self._store.tx() as tx:
            task = self._running(tx, task_id)
            m = self._require(tx, task.mission_id)
            clean = safe_text(message, 400)
            task.status, task.finished_at = "failed", self._clock()
            task.error = TaskError(kind=kind, message=clean, retryable=retryable)
            tx.save_task(task)
            can_retry = retryable and task.attempt < MAX_ATTEMPTS
            self._emit(
                tx,
                m.id,
                "task.failed",
                summary or f"{kind}: {clean}",
                task=task,
                status="failed",
                data={"kind": kind, "retryable": can_retry, "attempt": task.attempt},
            )
            if can_retry:
                m.resume_state = m.state
                self._set_state(tx, m, "NEEDS_RETRY")
            else:
                m.failure = f"{kind}: {clean}"
                self._close_open_work(tx, m)
                self._set_state(tx, m, "FAILED")
                self._emit(
                    tx,
                    m.id,
                    "mission.failed",
                    m.failure,
                    role="mission-director",
                    status="failed",
                )
        self.flush()
        return m

    def _running(self, tx: Tx, task_id: str) -> WorkflowTask:
        task = tx.task(task_id)
        if task is None:
            raise TaskNotFound(task_id)
        if task.status != "running":
            raise InvalidTransition(f"{task_id} is {task.status}, not running")
        return task

    def tool_event(
        self,
        task_id: str,
        tool: str,
        phase: str,
        ok: bool = True,
        summary: str | None = None,
        key: object = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        """A real tool call around real work: `phase` is started or completed. `key` tells
        apart repeated calls to one tool inside a task."""
        with self._store.tx() as tx:
            task = tx.task(task_id)
            if task is None:
                raise TaskNotFound(task_id)
            correlation = stable_id("call", task.id, task.attempt, tool, key)
            if phase == "started":
                self._emit(
                    tx,
                    task.mission_id,
                    "tool.started",
                    summary or tool,
                    tool,
                    key,
                    task=task,
                    status="running",
                    correlation_id=correlation,
                    data={"tool": tool, **(data or {})},
                )
            else:
                self._emit(
                    tx,
                    task.mission_id,
                    "tool.completed",
                    summary or tool,
                    tool,
                    key,
                    task=task,
                    status="succeeded" if ok else "failed",
                    correlation_id=correlation,
                    data={"tool": tool, "ok": ok, **(data or {})},
                )
        self.flush()

    # ── evidence and artifacts ──────────────────────────────────────────────────────────────

    def add_evidence(self, task_id: str, records: list[EvidenceRecord]) -> int:
        added = 0
        with self._store.tx() as tx:
            task = tx.task(task_id)
            if task is None:
                raise TaskNotFound(task_id)
            for r in records:
                if not tx.add_evidence(task.mission_id, r):
                    continue
                added += 1
                self._emit(
                    tx,
                    task.mission_id,
                    "evidence.created",
                    f"Evidence recorded for {r.account or r.entity_type}",
                    r.id,
                    task=task,
                    artifact_ids=[r.id],
                    data={"evidence": r.model_dump(mode="json")},
                )
        self.flush()
        return added

    def record_verification(self, task_id: str, records: list[EvidenceRecord]) -> None:
        with self._store.tx() as tx:
            task = tx.task(task_id)
            if task is None:
                raise TaskNotFound(task_id)
            for r in records:
                tx.update_evidence(task.mission_id, r)
            self._emit(
                tx,
                task.mission_id,
                "evidence.verified",
                f"Audited {len(records)} evidence records",
                task=task,
                data={
                    "results": {
                        r.id: {
                            "status": r.verification_status,
                            "reasons": r.verification_reasons,
                        }
                        for r in records
                    }
                },
            )
        self.flush()

    def publish_artifact(
        self, task_id: str, kind: str, artifact_id: str, summary: str, data: dict[str, Any]
    ) -> None:
        with self._store.tx() as tx:
            task = tx.task(task_id)
            if task is None:
                raise TaskNotFound(task_id)
            self._emit(
                tx,
                task.mission_id,
                "artifact.published",
                summary,
                artifact_id,
                task=task,
                artifact_ids=[artifact_id],
                data={"kind": kind, "id": artifact_id, "body": data},
            )
        self.flush()

    # ── approvals ───────────────────────────────────────────────────────────────────────────

    def request_approval(
        self, mission_id: str, gate: ApprovalGate, target_hash: str, summary: str
    ) -> WorkflowApproval:
        approval_id = stable_id("apr", mission_id, gate, target_hash)
        with self._store.tx() as tx:
            m = self._require(tx, mission_id)
            existing = tx.approval(approval_id)
            if existing is not None:
                return existing
            if m.state in TERMINAL:
                raise InvalidTransition(f"mission is {m.state}")
            for old in tx.approvals(mission_id):
                # Anything put up earlier described content that has since changed
                if old.gate == gate and old.status == "pending":
                    old.status, old.decided_at = "expired", self._clock()
                    tx.save_approval(old)
            state = m.resume_state if m.state == "WAITING_FOR_INPUT" else m.state
            if state == "USER_APPROVAL" and gate == "campaign_draft":
                state = "CAMPAIGN_DRAFTED"
            if state != GATE_STATES[gate]:
                raise InvalidTransition(f"{gate} needs {GATE_STATES[gate]}, mission is {state}")
            task: WorkflowTask | None = None
            if gate == "campaign_draft":
                checked = tx.task(f"{mission_id}.quality_gate")
                if checked is None or checked.status != "succeeded":
                    raise ApprovalMissing("the quality gate must pass before user review")
                task = tx.task(f"{mission_id}.user_review")
                if task is not None:
                    task.status, task.started_at = "waiting_approval", self._clock()
                    task.attempt = max(task.attempt, 1)
                    tx.save_task(task)
            if m.state == "WAITING_FOR_INPUT":
                m.wait_reason = None
                target = m.resume_state or m.state
                m.resume_state = None
                self._set_state(tx, m, target)
            if gate == "campaign_draft" and m.state != "USER_APPROVAL":
                self._set_state(tx, m, "USER_APPROVAL")
            approval = WorkflowApproval(
                id=approval_id,
                mission_id=mission_id,
                gate=gate,
                target_hash=target_hash,
                summary=safe_text(summary, 400),
                requested_at=self._clock(),
            )
            tx.save_approval(approval)
            self._emit(
                tx,
                mission_id,
                "approval.requested",
                summary,
                approval_id,
                task=task,
                role="mission-director",
                status="waiting_approval",
                artifact_ids=[approval_id],
                data={"approval": approval.model_dump(mode="json")},
            )
        self.flush()
        return approval

    def resolve_approval(
        self,
        approval_id: str,
        decision: Literal["approved", "rejected"],
        decided_by: str,
        expected_hash: str,
        reason: str | None = None,
    ) -> WorkflowApproval:
        """Records a human decision on this exact content. Sending is not part of any path."""
        with self._store.tx() as tx:
            a = tx.approval(approval_id)
            if a is None:
                raise ApprovalMissing(f"no approval {approval_id}")
            if a.target_hash != expected_hash:
                raise ApprovalMissing("the content changed after it was put up for approval")
            if a.status == decision:
                return a
            if a.status != "pending":
                raise ApprovalMissing(f"approval is already {a.status}")
            m = self._require(tx, a.mission_id)
            a.status, a.decided_at, a.decided_by = decision, self._clock(), decided_by
            a.reason = safe_text(reason, 400) if reason else None
            tx.save_approval(a)
            review = tx.task(f"{m.id}.user_review") if a.gate == "campaign_draft" else None
            self._emit(
                tx,
                m.id,
                "approval.resolved",
                f"{a.gate} {decision} by {decided_by}",
                a.id,
                task=review,
                role="mission-director",
                status="succeeded" if decision == "approved" else "failed",
                artifact_ids=[a.id],
                data={"approval": a.model_dump(mode="json")},
            )
            if decision != "approved":
                if review is not None:
                    review.status = "queued"
                    tx.save_task(review)
                self._to_waiting(tx, m, f"{a.gate} rejected: {a.reason or 'no reason given'}")
            elif review is not None:
                review.status, review.finished_at = "succeeded", self._clock()
                tx.save_task(review)
                self._emit(
                    tx,
                    m.id,
                    "task.completed",
                    "The user approved the draft. Nothing was sent.",
                    task=review,
                    status="succeeded",
                    artifact_ids=[a.id],
                )
                self._set_state(tx, m, "COMPLETE")
                self._emit(
                    tx,
                    m.id,
                    "mission.completed",
                    "Mission complete: draft approved, nothing sent",
                    role="mission-director",
                    status="succeeded",
                )
        self.flush()
        return a
