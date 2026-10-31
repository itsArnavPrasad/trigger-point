"""A researched account becomes an outreach target, carrying the signals that justified it, so the
learning loop can learn which signal actually leads to a meeting."""

from typing import Any

from tests.workflow.conftest import Rig, advance_to_draft
from tests.workflow.test_outreach import TEST_INBOX


def accounts(rig: Rig, mid: str) -> list[Any]:
    wf = rig.services.workflow
    return list(wf._research.get(wf.engine.mission(mid).research_id).accounts)  # noqa: SLF001


def first(rig: Rig, mid: str, status: str) -> Any:
    return next(a for a in accounts(rig, mid) if a.score.status == status)


def test_a_qualified_account_becomes_a_target_with_its_active_signals(rig: Rig) -> None:
    mid = advance_to_draft(rig)
    ar = first(rig, mid, "qualified")
    out = rig.services.workflow.target_from_account(
        mid, ar.account.provider_company_id, "school_authority"
    )
    active = [s for s in ar.signals if s.status == "active"]
    assert out["ok"] and out["source"] == "discovered" and out["name"] == ar.account.name
    assert out["account_id"] == ar.account.provider_company_id
    assert out["signal_types"] == sorted({s.type for s in active}) and out["signal_types"]
    assert out["why_now"] == [s.description for s in active]


def test_the_reason_for_reaching_out_never_enters_the_message_prompt(rig: Rig) -> None:
    mid = advance_to_draft(rig)
    ar = first(rig, mid, "qualified")
    out = rig.services.workflow.target_from_account(
        mid, ar.account.provider_company_id, "school_authority"
    )
    assert out["notes"] == ""  # notes feed the writer; the why-now stays on the target


def test_a_rejected_account_stays_out(rig: Rig) -> None:
    mid = advance_to_draft(rig)
    ar = first(rig, mid, "rejected")
    out = rig.services.workflow.target_from_account(
        mid, ar.account.provider_company_id, "school_authority"
    )
    assert out["ok"] is False and out["error"] == "not_qualified"
    assert rig.services.workflow.targets(mid) == []


def test_an_unknown_account_or_audience_is_a_typed_refusal(rig: Rig) -> None:
    mid = advance_to_draft(rig)
    wf = rig.services.workflow
    ar = first(rig, mid, "qualified")
    assert wf.target_from_account(mid, 999999, "school_authority")["error"] == "not_found"
    bad = wf.target_from_account(mid, ar.account.provider_company_id, "everyone")
    assert bad["ok"] is False and bad["error"] == "invalid_target"


def test_asking_twice_is_one_target(rig: Rig) -> None:
    mid = advance_to_draft(rig)
    wf = rig.services.workflow
    cid = first(rig, mid, "qualified").account.provider_company_id
    a = wf.target_from_account(mid, cid, "school_authority")
    b = wf.target_from_account(mid, cid, "school_authority")
    assert a["id"] == b["id"] and len(wf.targets(mid)) == 1


def test_a_mission_with_no_research_has_no_accounts_to_pick(rig: Rig) -> None:
    mid = str(
        rig.call("create_mission", website_url="supportpilot.example", goal="Book meetings")[
            "mission_id"
        ]
    )
    out = rig.services.workflow.target_from_account(mid, 1001, "school_authority")
    assert out["ok"] is False and out["error"] == "no_research"


def test_the_message_and_its_send_remember_which_signals_justified_it(rig: Rig) -> None:
    mid = advance_to_draft(rig)
    wf = rig.services.workflow
    wf.test_recipients = (TEST_INBOX,)
    cid = first(rig, mid, "qualified").account.provider_company_id
    target = wf.target_from_account(mid, cid, "school_authority")
    message = wf.write_outreach(mid, target["id"])
    assert message["ok"] and message["signal_types"] == target["signal_types"]
    assert message["account_id"] == cid
    wf.record_test_send(mid, message["id"], TEST_INBOX, "m1", "t1")
    touch = rig.services.feedback.touches(mid)[0]
    assert touch.signal_types == target["signal_types"]


def test_a_hand_named_target_has_no_signals_and_that_is_honest(rig: Rig) -> None:
    mid = advance_to_draft(rig)
    wf = rig.services.workflow
    t = wf.add_target(mid, {"name": "Sunrise", "audience": "parent"})
    message = wf.write_outreach(mid, t["id"])
    assert message["signal_types"] == [] and message["account_id"] is None


def test_the_agent_can_use_it_but_it_is_not_an_approval_tool(rig: Rig) -> None:
    tools = rig.tools()
    assert "target_from_account" in tools
