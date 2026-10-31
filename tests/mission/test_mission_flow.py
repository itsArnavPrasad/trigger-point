"""End-to-end replay flow: approved context -> mission -> discovery, through the JSON API."""

from typing import Any

from tests.conftest import MakeClient

GOAL = "Book meetings with B2B SaaS companies that are scaling their support teams"


def approved_context(client: Any) -> str:
    cid = client.post(
        "/api/contexts", json={"website_url": "supportpilot.example", "goal": GOAL}
    ).json()["context_id"]
    client.post(f"/api/contexts/{cid}/approve", json={"acknowledge_unsupported": True})
    return str(cid)


def test_mission_requires_an_approved_context(make_client: MakeClient) -> None:
    client, _ = make_client()
    cid = client.post(
        "/api/contexts", json={"website_url": "supportpilot.example", "goal": GOAL}
    ).json()["context_id"]
    r = client.post(f"/api/contexts/{cid}/missions")
    assert r.status_code == 409 and r.json()["detail"]["error"] == "context_not_approved"


def test_mission_compiles_to_a_reviewable_plan_with_estimate(make_client: MakeClient) -> None:
    client, _ = make_client()
    cid = approved_context(client)
    r = client.post(f"/api/contexts/{cid}/missions")
    assert r.status_code == 201
    mission = client.get(f"/api/missions/{r.json()['mission_id']}").json()
    assert mission["status"] == "review_required" and mission["mode"] == "replay"
    plan = mission["plan"]
    assert plan["countries"] and plan["employee_ranges"]
    assert "supportpilot.example" in plan["excluded_domains"]
    assert float(mission["estimated_credits"]) <= plan["credit_budget"]
    assert mission["search_request"]["search"]["query"]


def test_discovery_needs_approved_mission(make_client: MakeClient) -> None:
    client, _ = make_client()
    mid = client.post(f"/api/contexts/{approved_context(client)}/missions").json()["mission_id"]
    r = client.post(f"/api/missions/{mid}/discover")
    assert r.status_code == 409


def test_replay_discovery_dedupes_excludes_and_receipts(make_client: MakeClient) -> None:
    client, _ = make_client()
    mid = client.post(f"/api/contexts/{approved_context(client)}/missions").json()["mission_id"]
    client.post(f"/api/missions/{mid}/approve")
    r = client.post(f"/api/missions/{mid}/discover")
    assert r.status_code == 201, r.text
    run = client.get(f"/api/discoveries/{r.json()['discovery_id']}").json()
    assert run["mode"] == "replay" and run["outcome"] == "completed"
    names = [a["name"] for a in run["accounts"]]
    assert len(names) == len(set(names))
    rejected = {x["name"]: x["reason"] for x in run["rejected"]}
    assert rejected["SupportPilot"] == "seller_itself"
    assert any(reason == "duplicate" for reason in rejected.values())
    endpoints = [c["endpoint"] for c in run["calls"]]
    assert endpoints[:3] == ["/account/endpoints", "/company/identify", "/company/search"]
    assert all(c["mode"] == "replay" for c in run["calls"])
    assert run["credits"]["actual"] == "0"
    assert run["accounts"][0]["provider_company_id"]
    assert all(a["retrieved_at"] for a in run["accounts"])
