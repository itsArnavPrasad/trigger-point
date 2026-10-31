"""The ICP is a versioned strategy record, not just a search filter."""

from tests.research.factories import plan
from tests.workflow.conftest import GOAL, URL, Rig
from trigger_point.workflow.icp import build_icp


def ready(rig: Rig) -> str:
    mid = str(rig.call("create_mission", website_url=URL, goal=GOAL)["mission_id"])
    a = rig.call("request_user_approval", mission_id=mid, gate="business_profile")
    rig.call(
        "approve_business_profile",
        mission_id=mid,
        approval_id=a["approval_id"],
        acknowledge_unsupported=True,
    )
    rig.call("build_icp", mission_id=mid)
    return mid


def test_criteria_split_must_haves_preferences_and_disqualifiers() -> None:
    icp = build_icp(plan(), "wm_1", "p1", 1, "Mission Director", "first", None, "h")
    kinds = {c.kind for c in icp.criteria}
    assert {"must_have", "preference", "disqualifier"} <= kinds
    assert icp.status == "hypothesis" and icp.version == 1
    assert all(c.confidence in ("high", "medium", "low") for c in icp.criteria)


def test_dimensions_with_no_evidence_are_listed_as_gaps_not_guessed() -> None:
    icp = build_icp(plan(), "wm_1", "p1", 1, "x", "first", None, "h")
    assert "budget" in icp.gaps
    assert not any(c.dimension == "budget" for c in icp.criteria)


def test_a_new_version_says_what_changed() -> None:
    first = build_icp(plan(), "wm_1", "p1", 1, "x", "first", None, "h")
    revised = plan().model_copy(update={"countries": ["CAN"]})
    second = build_icp(revised, "wm_1", "p1", 2, "user", "Canada first", first, "h2")
    assert second.version == 2 and any("CAN" in c for c in second.changes)


def test_building_the_icp_records_version_one_and_an_event(rig: Rig) -> None:
    mid = ready(rig)
    versions = rig.services.workflow.engine.icp_versions(mid)
    assert [v.version for v in versions] == [1]
    assert "strategy.versioned" in rig.event_types(mid)


def test_editing_the_icp_makes_a_new_version_and_needs_new_approval(rig: Rig) -> None:
    mid = ready(rig)
    old = rig.call("request_user_approval", mission_id=mid, gate="icp_plan")
    out = rig.services.workflow.edit_icp(mid, {"countries": ["CAN"]}, "Focus on Canada")
    assert out["ok"] and out["version"] == 2
    gone = rig.call("approve_icp_plan", mission_id=mid, approval_id=old["approval_id"])
    assert gone["ok"] is False
    assert rig.services.workflow.engine.approval(old["approval_id"]).status == "expired"
    new = rig.call("request_user_approval", mission_id=mid, gate="icp_plan")
    assert rig.call("approve_icp_plan", mission_id=mid, approval_id=new["approval_id"])["ok"]
    versions = rig.services.workflow.engine.icp_versions(mid)
    assert [v.status for v in versions] == ["superseded", "approved"]


def test_the_icp_cannot_change_after_discovery_started(rig: Rig) -> None:
    mid = ready(rig)
    a = rig.call("request_user_approval", mission_id=mid, gate="icp_plan")
    rig.call("approve_icp_plan", mission_id=mid, approval_id=a["approval_id"])
    rig.call("discover_accounts", mission_id=mid)
    assert rig.services.workflow.edit_icp(mid, {"countries": ["CAN"]}, "x")["ok"] is False
