"""Create, verify, revise once, edit and approve first-touch drafts. Nothing is ever sent."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from trigger_point.cases.models import AccountCase
from trigger_point.cases.service import CaseService
from trigger_point.drafts.models import (
    CampaignDraft,
    DraftWire,
    Finding,
    VerifierAttempt,
    content_hash,
)
from trigger_point.drafts.prompt import (
    DRAFT_SYSTEM_PROMPT,
    build_draft_message,
    build_revision_message,
)
from trigger_point.drafts.verifier import passes, verify_draft
from trigger_point.llm.base import LlmError, LlmRequest, LlmResponse, StructuredLlm
from trigger_point.models.evidence import evidence_id
from trigger_point.store.db import Store


class DraftNotAllowed(RuntimeError):
    pass


class DraftNotFound(LookupError):
    pass


class DraftStateError(RuntimeError):
    pass


class DraftFailed(RuntimeError):
    pass


class DraftService:
    def __init__(
        self,
        store: Store,
        cases: CaseService,
        llm: StructuredLlm,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store, self._cases, self._llm, self._clock = store, cases, llm, clock

    def get(self, draft_id: str) -> CampaignDraft:
        draft = self._store.get_draft(draft_id)
        if draft is None:
            raise DraftNotFound(draft_id)
        return draft

    def _others(self, case: AccountCase) -> list[str]:
        run = self._store.get_research(case.research_id)
        return [
            a.account.name
            for a in (run.accounts if run else [])
            if a.account.name and a.account.provider_company_id != case.account_id
        ]

    def _complete(self, task: str, case: AccountCase, user: str) -> LlmResponse[DraftWire]:
        key = f"{case.account_domain or 'account'}__{case.account_id}"
        try:
            return self._llm.complete(
                LlmRequest(
                    task=task,
                    replay_key=key,
                    system=DRAFT_SYSTEM_PROMPT,
                    user=user,
                    schema=DraftWire,
                    max_tokens=8000,
                )
            )
        except LlmError as exc:
            raise DraftFailed(str(exc)) from exc

    def create(self, research_id: str, account_id: int, initiated_by: str = "ui") -> CampaignDraft:
        case = self._cases.get_or_build(research_id, account_id)
        if case.recommended_route != "cold_email" or case.recipient is None:
            raise DraftNotAllowed(f"{case.recommended_route}: {case.route_reason}")
        others = self._others(case)
        log: list[VerifierAttempt] = []
        calls: list[dict[str, object]] = []

        resp = self._complete("first_touch_draft", case, build_draft_message(case))
        wire = resp.output
        findings = verify_draft(wire, case, others)
        log.append(
            VerifierAttempt(
                attempt=1,
                outcome="pass" if passes(findings) else "fail",
                findings=findings,
                source="llm",
            )
        )
        calls.append(_usage("first_touch_draft", resp))
        if not passes(findings):
            resp = self._complete(
                "first_touch_revision", case, build_revision_message(case, wire, findings)
            )
            wire = resp.output
            findings = verify_draft(wire, case, others)
            log.append(
                VerifierAttempt(
                    attempt=2,
                    outcome="pass" if passes(findings) else "fail",
                    findings=findings,
                    source="llm_revision",
                )
            )
            calls.append(_usage("first_touch_revision", resp))

        person = case.recipient.person
        draft = CampaignDraft(
            id=evidence_id("draft", case.id, self._clock().isoformat()),
            case_id=case.id,
            research_id=research_id,
            account_id=account_id,
            account_name=case.account_name,
            recipient_person_id=person.provider_person_id,
            recipient_name=person.name,
            recipient_title=person.current_title,
            subject=wire.subject,
            body=wire.body,
            hook_evidence_id=wire.hook_evidence_id,
            proof_point_evidence_id=wire.proof_point_evidence_id or None,
            claims=wire.claims,
            follow_ups=wire.follow_ups,
            content_hash=content_hash(person.provider_person_id, "email", wire.subject, wire.body),
            status="verified" if passes(findings) else "rejected",
            verifier_log=log,
            mode=resp.mode,
            llm_calls=calls,
            initiated_by=initiated_by,
            created_at=self._clock(),
        )
        self._store.save_draft(draft)
        return draft

    def edit(self, draft_id: str, subject: str, body: str) -> CampaignDraft:
        """A human edit is re-verified deterministically and always clears any approval."""
        draft = self.get(draft_id)
        case = self._cases.get_or_build(draft.research_id, draft.account_id)
        wire = DraftWire(
            subject=subject,
            body=body,
            hook_evidence_id=draft.hook_evidence_id,
            proof_point_evidence_id=draft.proof_point_evidence_id or "",
            claims=draft.claims,
            follow_ups=draft.follow_ups,
        )
        findings: list[Finding] = verify_draft(wire, case, self._others(case))
        attempt = VerifierAttempt(
            attempt=len(draft.verifier_log) + 1,
            outcome="pass" if passes(findings) else "fail",
            findings=findings,
            source="human_edit",
        )
        edited = draft.model_copy(
            update={
                "subject": subject,
                "body": body,
                "content_hash": content_hash(
                    draft.recipient_person_id, draft.channel, subject, body
                ),
                "status": "verified" if passes(findings) else "rejected",
                "verifier_log": [*draft.verifier_log, attempt],
                "approved_at": None,
                "approved_by": None,
                "approved_hash": None,
            }
        )
        self._store.save_draft(edited)
        return edited

    def approve(self, draft_id: str, expected_hash: str, approver: str) -> CampaignDraft:
        """Records approval of this exact recipient, channel and content. Does not send."""
        draft = self.get(draft_id)
        if draft.status != "verified":
            raise DraftStateError(f"only verified drafts can be approved (status {draft.status})")
        if expected_hash != draft.content_hash:
            raise DraftStateError("content hash mismatch: the draft changed after you reviewed it")
        approved = draft.model_copy(
            update={
                "status": "approved",
                "approved_at": self._clock(),
                "approved_by": approver,
                "approved_hash": draft.content_hash,
            }
        )
        self._store.save_draft(approved)
        return approved


def _usage(task: str, resp: LlmResponse[DraftWire]) -> dict[str, object]:
    u = resp.usage
    return {
        "task": task,
        "mode": resp.mode,
        **(
            {
                "model": u.model,
                "input_tokens": u.input_tokens,
                "output_tokens": u.output_tokens,
                "latency_ms": u.latency_ms,
            }
            if u
            else {}
        ),
    }
