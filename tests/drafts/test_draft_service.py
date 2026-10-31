"""Draft service over a real replayed research run, with a scripted LLM for the draft step."""

from pathlib import Path
from typing import Any

import pytest

from tests.conftest import FIXTURES
from trigger_point.api.app import AppDeps, Services, build_services
from trigger_point.config import load_settings
from trigger_point.context.extractor import LlmContextExtractor
from trigger_point.drafts.models import DraftClaim, DraftWire, FollowUpStep
from trigger_point.drafts.service import DraftNotAllowed, DraftStateError
from trigger_point.llm.base import LlmRequest, LlmResponse
from trigger_point.llm.replay import ReplayStructuredLlm
from trigger_point.store.db import Store
from trigger_point.web.fetcher import FixtureFetcher

GOAL = "Book meetings with B2B SaaS companies that are scaling their support teams"


class ScriptedLlm:
    """Replays context/mission fixtures; returns scripted outputs for draft tasks."""

    def __init__(self) -> None:
        self.replay = ReplayStructuredLlm(FIXTURES / "llm")
        self.drafts: list[Any] = []
        self.requests: list[LlmRequest[Any]] = []

    @property
    def mode(self) -> str:
        return "replay"

    def complete(self, req: LlmRequest[Any]) -> LlmResponse[Any]:
        if req.task.startswith("first_touch"):
            self.requests.append(req)
            make = self.drafts.pop(0)
            return LlmResponse(output=make(req), usage=None, mode="replay")
        return self.replay.complete(req)


def pipeline(tmp_path: Path) -> tuple[Services, ScriptedLlm, str, dict[str, int]]:
    llm = ScriptedLlm()
    settings = load_settings({"DATABASE_URL": f"sqlite:///{tmp_path / 'd.db'}"})
    services = build_services(
        settings,
        AppDeps(
            FixtureFetcher(FIXTURES / "sites"),
            LlmContextExtractor(llm),
            Store(tmp_path / "d.db"),
            llm,
        ),
    )  # type: ignore[arg-type]
    out = services.contexts.intake("supportpilot.example", GOAL)
    services.contexts.approve(out.context_id, "test", acknowledge_unsupported=True)
    m = services.missions.compile(out.context_id)
    services.missions.approve(m.id)
    d = services.discovery.run(m.id)
    r = services.research.run(d.id)
    ids = {a.account.name or "": a.account.provider_company_id for a in r.accounts}
    return services, llm, r.id, ids


def good_draft(case: Any) -> DraftWire:
    hook = next(
        e
        for e in case.evidence
        if e.id in case.hook_evidence_ids and e.source_kind == "job_posting"
    )
    proof = next(e for e in case.evidence if e.id in case.seller_evidence_ids and "45%" in e.claim)
    first = case.recipient.person.name.split()[0]
    body = (
        f"Hi {first},\n\n{case.account_name} is hiring for support ({hook.excerpt}). Teams in "
        f"that spot often start by deflecting repetitive tickets. SupportPilot automatically "
        f"resolves up to 45% of inbound tickets for teams handling more than 5,000 tickets "
        f"per month. Would a short call next week be useful?\n\n[Your name]"
    )
    return DraftWire(
        subject=f"Support hiring at {case.account_name}",
        body=body,
        hook_evidence_id=hook.id,
        proof_point_evidence_id=proof.id,
        claims=[
            DraftClaim(
                text=f"{case.account_name} is hiring for support",
                kind="fact",
                evidence_ids=[hook.id],
            ),
            DraftClaim(text="up to 45% of inbound tickets", kind="fact", evidence_ids=[proof.id]),
        ],
        follow_ups=[FollowUpStep(day_offset=4, angle="integration angle", evidence_ids=[proof.id])],
    )


def test_verified_draft_is_hash_bound_and_approval_never_sends(tmp_path: Path) -> None:
    services, llm, rid, ids = pipeline(tmp_path)
    case = services.cases.get_or_build(rid, ids["Ledgerloop"])
    llm.drafts.append(lambda req: good_draft(case))
    draft = services.drafts.create(rid, ids["Ledgerloop"])
    assert draft.status == "verified" and draft.sending == "disabled"
    assert draft.recipient_name == "Maya Example" and len(draft.content_hash) == 64
    assert [a.outcome for a in draft.verifier_log] == ["pass"]
    prompt = llm.requests[0].user
    assert all(eid in prompt for eid in case.hook_evidence_ids)
    assert "Quartzdesk" not in prompt  # other prospects are never shown to the writer

    with pytest.raises(DraftStateError, match="hash"):
        services.drafts.approve(draft.id, expected_hash="0" * 64, approver="u")
    approved = services.drafts.approve(draft.id, expected_hash=draft.content_hash, approver="u")
    assert approved.status == "approved" and approved.approved_hash == draft.content_hash


def test_failed_first_draft_is_revised_once_with_findings(tmp_path: Path) -> None:
    services, llm, rid, ids = pipeline(tmp_path)
    case = services.cases.get_or_build(rid, ids["Ledgerloop"])
    bad = good_draft(case).model_copy(
        update={"body": good_draft(case).body.replace("up to 45%", "70%")}
    )
    llm.drafts += [lambda req: bad, lambda req: good_draft(case)]
    draft = services.drafts.create(rid, ids["Ledgerloop"])
    assert [a.outcome for a in draft.verifier_log] == ["fail", "pass"]
    assert draft.verifier_log[0].findings[0].code == "unsupported_number"
    assert "unsupported_number" in llm.requests[1].user  # findings fed back
    assert draft.status == "verified"


def test_twice_failing_draft_is_rejected_and_not_approvable(tmp_path: Path) -> None:
    services, llm, rid, ids = pipeline(tmp_path)
    case = services.cases.get_or_build(rid, ids["Ledgerloop"])
    bad = good_draft(case).model_copy(update={"body": "Hi! As we discussed, quick question?"})
    llm.drafts += [lambda req: bad, lambda req: bad]
    draft = services.drafts.create(rid, ids["Ledgerloop"])
    assert draft.status == "rejected"
    with pytest.raises(DraftStateError, match="verified"):
        services.drafts.approve(draft.id, expected_hash=draft.content_hash, approver="u")


def test_rejected_account_cannot_be_drafted(tmp_path: Path) -> None:
    services, _, rid, ids = pipeline(tmp_path)
    with pytest.raises(DraftNotAllowed, match="no_relevant_buyer"):
        services.drafts.create(rid, ids["Orbitly"])


def test_human_edit_is_reverified_and_clears_approval(tmp_path: Path) -> None:
    services, llm, rid, ids = pipeline(tmp_path)
    case = services.cases.get_or_build(rid, ids["Ledgerloop"])
    llm.drafts.append(lambda req: good_draft(case))
    draft = services.drafts.create(rid, ids["Ledgerloop"])
    services.drafts.approve(draft.id, draft.content_hash, "u")
    edited = services.drafts.edit(
        draft.id, subject=draft.subject, body=draft.body.replace("up to 45%", "90%")
    )
    assert edited.status == "rejected" and edited.approved_at is None
    assert edited.verifier_log[-1].source == "human_edit"
    assert edited.content_hash != draft.content_hash
