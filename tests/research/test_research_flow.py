"""Full replay flow through the JSON API: context -> mission -> discovery -> research."""

from typing import Any

from tests.conftest import MakeClient

GOAL = "Book meetings with B2B SaaS companies that are scaling their support teams"


def researched(client: Any) -> dict[str, Any]:
    cid = client.post(
        "/api/contexts", json={"website_url": "supportpilot.example", "goal": GOAL}
    ).json()["context_id"]
    client.post(f"/api/contexts/{cid}/approve", json={"acknowledge_unsupported": True})
    mid = client.post(f"/api/contexts/{cid}/missions").json()["mission_id"]
    client.post(f"/api/missions/{mid}/approve")
    did = client.post(f"/api/missions/{mid}/discover").json()["discovery_id"]
    r = client.post(f"/api/discoveries/{did}/research")
    assert r.status_code == 201, r.text
    return dict(client.get(f"/api/research/{r.json()['research_id']}").json())


def test_replay_research_tells_an_honest_story(make_client: MakeClient) -> None:
    client, _ = make_client()
    run = researched(client)
    assert run["mode"] == "replay" and run["reference_date"] == "2026-10-31"
    by_name = {a["account"]["name"]: a for a in run["accounts"]}

    ledger = by_name["Ledgerloop"]
    assert ledger["score"]["status"] == "qualified"
    assert ledger["best_person"]["person"]["current_title"] == "Head of Support"
    assert any("Zendesk" in e["claim"] for e in ledger["evidence"])
    assert any(
        s["type"] == "support_team_growth" and s["status"] == "active" for s in ledger["signals"]
    )

    # No dated reason is no longer a rejection: Fernwood was people-searched, and found no buyer.
    assert by_name["Fernwood Billing"]["score"]["rejections"] == ["no_relevant_buyer"]
    orbitly = by_name["Orbitly"]
    assert "no_relevant_buyer" in orbitly["score"]["rejections"]
    assert orbitly["people_rejected"][0]["reason"] == "current_employer_mismatch"

    assert run["accounts"][0]["account"]["name"] == "Ledgerloop"  # ranked first
    assert [c["endpoint"] for c in run["calls"]] == ["/job/search", "/person/search"]
    assert all(c["replay_source"].startswith("synthetic demo fixture") for c in run["calls"])
    assert all(a["score"]["version"] == "score-v1" for a in run["accounts"])
