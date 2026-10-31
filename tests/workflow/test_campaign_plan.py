"""The next campaign is proposed from what was learned, then a person approves it.

Code, not the model, checks that each change cites real evidence and that a pattern needs two
independent sources; anything thinner is an experiment, kept out of the standing lessons."""

from typing import Any

from tests.workflow.conftest import Rig
from tests.workflow.test_feedback import meeting_with
from tests.workflow.test_outreach import ready
from trigger_point.workflow.feedback import FeedbackService

CAMPAIGN = {
    "audience": "school_authority",
    "signal_type": "topic_engagement",
    "angle": "Lead with teacher buy-in, then a one-class pilot",
    "why": "Principals asked for teacher buy-in before anything else",
}


def learned(rig: Rig) -> tuple[FeedbackService, str, list[str], list[str]]:
    """Two meetings, each with one learning: two independent sources."""
    wf, fb = rig.services.workflow, rig.services.feedback
    mid = ready(rig)
    wf.build_strategy(mid)
    meeting_with(wf, mid, "Sunrise call", ["Teacher buy-in comes first"])
    meeting_with(wf, mid, "Moonrise call", ["Teachers decide before principals"])
    ids = [i["id"] for i in fb.insights(mid)]
    return fb, mid, ids, ids[:1]


def change(text: str, ids: list[str], **over: Any) -> dict[str, Any]:
    return {"text": text, "target": "messaging", "evidence_ids": ids, **over}


def propose(fb: FeedbackService, mid: str, changes: list[dict[str, Any]]) -> dict[str, Any]:
    return fb.propose_campaign_plan(mid, "Next term: teachers first", changes, CAMPAIGN)


def test_a_plan_cites_the_evidence_behind_each_change_and_waits_for_a_person(rig: Rig) -> None:
    fb, mid, both, _ = learned(rig)
    plan = propose(fb, mid, [change("Lead with teacher buy-in", both)])
    assert plan["ok"] and plan["status"] == "proposed"
    assert plan["changes"][0]["sources"] == 2 and plan["changes"][0]["experiment"] is False
    assert fb.plans(mid)[0]["id"] == plan["id"]
    assert len(rig.services.workflow.strategy_versions(mid)) == 1  # nothing changed yet


def test_evidence_that_does_not_exist_is_refused(rig: Rig) -> None:
    fb, mid, *_ = learned(rig)
    out = propose(fb, mid, [change("Invented", ["ins_nope"])])
    assert out["ok"] is False and out["error"] == "unsupported" and out["ids"] == ["ins_nope"]


def test_a_change_with_no_evidence_is_refused(rig: Rig) -> None:
    fb, mid, *_ = learned(rig)
    assert propose(fb, mid, [change("Hunch", [])])["error"] == "unsupported"


def test_a_plan_with_nothing_in_it_is_refused(rig: Rig) -> None:
    fb, mid, *_ = learned(rig)
    assert propose(fb, mid, [])["error"] == "empty_plan"


def test_one_source_is_not_a_pattern_unless_it_is_labelled_an_experiment(rig: Rig) -> None:
    fb, mid, _, one = learned(rig)
    refused = propose(fb, mid, [change("Lead with teacher buy-in", one)])
    assert refused["ok"] is False and refused["error"] == "one_source" and refused["index"] == 0
    accepted = propose(fb, mid, [change("Try a teacher-first opener", one, experiment=True)])
    assert accepted["ok"] and accepted["changes"][0]["experiment"] is True


def test_a_rejected_insight_cannot_back_a_plan(rig: Rig) -> None:
    fb, mid, both, _ = learned(rig)
    fb.review_insight(mid, both[0], "reject")
    assert propose(fb, mid, [change("Teacher buy-in", both)])["error"] == "unsupported"


def test_approval_makes_one_version_one_experiment_and_a_lesson_per_backed_change(
    rig: Rig,
) -> None:
    fb, mid, both, one = learned(rig)
    wf = rig.services.workflow
    plan = propose(
        fb,
        mid,
        [
            change("Lead with teacher buy-in", both),
            change("Try a teacher-first opener", one, experiment=True),
        ],
    )
    out = fb.decide_campaign_plan(mid, plan["id"], "approved")
    versions = wf.strategy_versions(mid)
    assert out["ok"] and out["version"] == versions[-1]["version"] == 2
    assert versions[-1]["changes"] == ["Lead with teacher buy-in", "Try a teacher-first opener"]
    assert versions[-1]["body"]["next_campaign"]["angle"] == CAMPAIGN["angle"]
    approved = [x for x in fb.lessons(mid) if x["status"] == "approved"]
    assert [x["text"] for x in approved] == [
        "Lead with teacher buy-in"
    ]  # the experiment is no lesson
    assert approved[0]["strategy_version"] == 2
    assert len([e for e in fb.experiments(mid) if e["version"] == 2]) == 1
    assert fb.plans(mid)[0]["status"] == "approved"


def test_a_rejected_plan_changes_nothing(rig: Rig) -> None:
    fb, mid, both, _ = learned(rig)
    plan = propose(fb, mid, [change("Lead with teacher buy-in", both)])
    assert fb.decide_campaign_plan(mid, plan["id"], "rejected")["status"] == "rejected"
    assert len(rig.services.workflow.strategy_versions(mid)) == 1
    assert fb.lessons(mid) == [] and fb.plans(mid)[0]["status"] == "rejected"


def test_a_plan_is_decided_once(rig: Rig) -> None:
    fb, mid, both, _ = learned(rig)
    plan = propose(fb, mid, [change("Lead with teacher buy-in", both)])
    fb.decide_campaign_plan(mid, plan["id"], "approved")
    again = fb.decide_campaign_plan(mid, plan["id"], "approved")
    assert again["error"] == "already_decided"
    assert len(rig.services.workflow.strategy_versions(mid)) == 2


def test_an_unknown_plan_is_a_typed_refusal(rig: Rig) -> None:
    fb, mid, *_ = learned(rig)
    assert fb.decide_campaign_plan(mid, "plan_x", "approved")["error"] == "not_found"


def test_an_approved_signal_change_steers_the_next_missions_icp(rig: Rig) -> None:
    fb, mid, both, _ = learned(rig)
    plan = propose(
        fb,
        mid,
        [
            change(
                "Give recent funding more weight",
                both,
                target="qualification",
                dimension="signal_type",
                value="recent_funding",
            )
        ],
    )
    fb.decide_campaign_plan(mid, plan["id"], "approved")
    icp = rig.services.workflow.build_icp(ready(rig, "Reach more schools next term"))
    assert "recent_funding" in icp["signal_types"]


def test_the_agent_can_propose_but_only_a_person_can_approve(rig: Rig) -> None:
    names = set(rig.tools())
    assert "propose_campaign_plan" in names and "decide_campaign_plan" not in names


def test_the_view_lists_the_plans(rig: Rig) -> None:
    fb, mid, both, _ = learned(rig)
    propose(fb, mid, [change("Lead with teacher buy-in", both)])
    assert len(fb.view(mid)["plans"]) == 1
