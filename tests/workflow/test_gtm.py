"""Strategy, outcomes, pipeline, learning and finance: real records, honest arithmetic."""

from datetime import date
from typing import Any

import pytest

from tests.workflow.conftest import GOAL, URL, Rig, advance_to_draft
from trigger_point.workflow.gtm import (
    MIN_SAMPLE,
    Outcome,
    build_pipeline,
    finance_metrics,
    label_strategy,
    propose_changes,
)
from trigger_point.workflow.strategy import StrategyDraft


def outcome(
    kind: str = "meeting_held", mode: str = "live", account: int = 1, **over: Any
) -> Outcome:
    base = {
        "id": f"o{account}{kind}",
        "mission_id": "m",
        "account_id": account,
        "account_name": f"A{account}",
        "kind": kind,
        "occurred_on": date(2026, 10, 2),
        "mode": mode,
        "signal_type": "support_team_growth",
    }
    return Outcome.model_validate({**base, **over})


def draft(**over: Any) -> StrategyDraft:
    base: dict[str, Any] = {
        "market_category": "Support automation",
        "adjacent_categories": [],
        "competitors": [
            {"name": "Zendesk", "type": "direct", "basis": "stated"},
            {"name": "Acme", "type": "direct", "basis": "stated"},
        ],
        "market_gaps": [],
        "differentiation_hypotheses": [],
        "value_proposition": {
            "target_segment": "SaaS support teams",
            "problem": "Ticket volume",
            "current_alternative": "Hiring",
            "outcome": "Faster replies",
            "differentiation": "Native",
            "proof": "Resolves 90% of tickets",
            "customer_language": "Answer customers faster",
        },
        "capability_outcomes": [],
        "positioning": "x",
        "message_pillars": [],
        "stakeholder_messages": [],
        "claims_needing_proof": [],
        "gtm_motion": {"motion": "outbound", "why": "x", "alternatives_rejected": []},
        "channels": [
            {
                "channel": "email",
                "audience": "a",
                "purpose": "p",
                "offer": "o",
                "timing": "t",
                "owner": "you",
                "success_metric": "m",
            },
            {
                "channel": "events",
                "audience": "a",
                "purpose": "p",
                "offer": "o",
                "timing": "t",
                "owner": "you",
                "success_metric": "m",
            },
        ],
        "experiments": [],
        "open_questions": [],
    }
    return StrategyDraft.model_validate({**base, **over})


def test_a_competitor_is_observed_only_if_the_approved_profile_names_it() -> None:
    out = label_strategy(draft(), known_competitors=["Zendesk"], proof_points=[])
    basis = {c.name: c.basis for c in out.competitors}
    assert basis == {"Zendesk": "stated", "Acme": "inferred"}


def test_unapproved_proof_is_flagged_not_kept() -> None:
    out = label_strategy(draft(), known_competitors=[], proof_points=["SOC 2 certified"])
    assert out.value_proposition.proof == ""
    assert "Resolves 90% of tickets" in out.claims_needing_proof


def test_channels_say_whether_a_real_integration_exists() -> None:
    out = label_strategy(draft(), [], [])
    assert {c.channel: c.availability for c in out.channels} == {
        "email": "draft_only",
        "events": "manual",
    }


def test_strategy_step_versions_a_labelled_hypothesis(rig: Rig) -> None:
    mid = advance_to_draft(rig)
    versions = rig.services.workflow.strategy_versions(mid)
    assert [v["version"] for v in versions] == [1]
    assert versions[0]["status"] == "hypothesis" and versions[0]["mode"] == "replay"
    assert versions[0]["body"]["value_proposition"]["target_segment"]


def test_strategy_needs_the_approved_profile(rig: Rig) -> None:
    mid = rig.call("create_mission", website_url=URL, goal=GOAL)["mission_id"]
    assert rig.call("build_strategy", mission_id=mid)["error"] == "approval_missing"


def test_pipeline_uses_the_furthest_stage_and_never_counts_pipeline_as_revenue() -> None:
    rows = [
        outcome("meeting_held", account=1),
        outcome("opportunity_created", account=1, value=5000, currency="USD"),
        outcome("closed_won", account=2, value=9000, currency="USD"),
    ]
    p = build_pipeline(rows)
    assert {a["account_id"]: a["stage"] for a in p["accounts"]} == {
        1: "opportunity_created",
        2: "closed_won",
    }
    assert p["open_pipeline"] == {"USD": 5000} and p["won_revenue"] == {"USD": 9000}


def test_a_later_loss_closes_the_opportunity() -> None:
    rows = [
        outcome("opportunity_created", value=5000, currency="USD"),
        outcome("closed_lost", occurred_on=date(2026, 10, 10), reason="budget"),
    ]
    p = build_pipeline(rows)
    assert p["accounts"][0]["stage"] == "closed_lost" and p["open_pipeline"] == {}


def test_learning_ignores_fixture_outcomes_entirely() -> None:
    rows = [outcome(mode="replay", account=i) for i in range(50)]
    out = propose_changes(rows)
    assert out["proposals"] == [] and out["excluded_fixture"] == 50


def test_learning_refuses_a_small_sample() -> None:
    rows = [outcome(account=i) for i in range(MIN_SAMPLE - 1)]
    out = propose_changes(rows)
    assert out["proposals"] == []
    assert "support_team_growth" in out["too_small"]


def test_learning_proposes_with_evidence_and_says_it_is_correlation() -> None:
    rows = [outcome(account=i) for i in range(MIN_SAMPLE)]
    rows += [
        outcome("reply", account=100 + i, signal_type="active_hiring") for i in range(MIN_SAMPLE)
    ]
    out = propose_changes(rows)
    p = out["proposals"][0]
    assert p["signal"] == "support_team_growth" and p["sample"] == MIN_SAMPLE
    assert "correlation" in p["caveat"].lower() and p["outcome_ids"]


def test_finance_shows_no_number_it_cannot_support() -> None:
    m = finance_metrics(usd_actual=10.0, usd_estimated=5.0, accounts=5, qualified=0, meetings=0)
    assert m["cost_per_account"] == 2.0
    assert m["cost_per_qualified"] is None and m["cost_per_meeting"] is None
    assert m["usd_actual"] == 10.0 and m["usd_estimated"] == 5.0


def test_outcomes_flow_through_the_service(rig: Rig) -> None:
    mid = advance_to_draft(rig)
    wf = rig.services.workflow
    out = wf.record_outcome(
        mid, {"account_name": "Ledgerloop", "kind": "meeting_booked", "occurred_on": "2026-10-21"}
    )
    assert out["ok"] and wf.outcomes(mid)[0].mode == "replay"
    assert wf.record_outcome(mid, {"kind": "nonsense"})["ok"] is False


def test_a_meeting_note_keeps_its_source_and_records_the_outcome(rig: Rig) -> None:
    mid = advance_to_draft(rig)
    wf = rig.services.workflow
    wf.add_meeting(
        mid,
        {
            "title": "Intro",
            "held_on": "2026-10-22",
            "account_name": "Ledgerloop",
            "notes": "They use Zendesk",
        },
    )
    assert wf.meetings(mid)[0]["source"] == "manual"
    assert [o.kind for o in wf.outcomes(mid)] == ["meeting_held"]


def test_a_future_meeting_counts_as_booked_not_held(rig: Rig) -> None:
    mid = advance_to_draft(rig)
    wf = rig.services.workflow
    wf.add_meeting(mid, {"title": "Intro", "held_on": "2999-01-01", "account_name": "Ledgerloop"})
    assert [o.kind for o in wf.outcomes(mid)] == ["meeting_booked"]


def test_a_missed_meeting_records_no_outcome(rig: Rig) -> None:
    mid = advance_to_draft(rig)
    wf = rig.services.workflow
    wf.add_meeting(mid, {"title": "Walk-in", "held_on": "2026-10-30", "status": "missed"})
    assert wf.meetings(mid)[0]["status"] == "missed" and wf.outcomes(mid) == []


def test_a_proposal_needs_approval_creates_a_version_and_can_roll_back(rig: Rig) -> None:
    mid = advance_to_draft(rig)
    wf = rig.services.workflow
    p = wf.add_proposal(mid, "Lead with hiring signals", "12 of 40 converted", ["o1"])
    assert len(wf.strategy_versions(mid)) == 1
    assert wf.decide_proposal(mid, p["id"], "approved")["version"] == 2
    assert wf.strategy_versions(mid)[-1]["changes"] == ["Lead with hiring signals"]
    assert wf.rollback_strategy(mid, 1)["version"] == 3
    last = wf.strategy_versions(mid)[-1]
    assert last["rolled_back_to"] == 1 and last["body"] == wf.strategy_versions(mid)[0]["body"]


def test_a_decided_proposal_cannot_be_decided_again(rig: Rig) -> None:
    mid = advance_to_draft(rig)
    wf = rig.services.workflow
    p = wf.add_proposal(mid, "x", "y", [])
    wf.decide_proposal(mid, p["id"], "rejected")
    assert wf.decide_proposal(mid, p["id"], "approved")["ok"] is False


@pytest.mark.parametrize(("title", "first"), [("Head of Support", 2), ("Support Lead", 1)])
def test_committee_sequence_starts_nearest_the_problem(title: str, first: int) -> None:
    from trigger_point.office.views import stakeholder_plan

    assert stakeholder_plan(title)["sequence"] == first
