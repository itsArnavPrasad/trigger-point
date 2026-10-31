"""Replay end to end through the JSON API and UI: research -> case -> draft -> approve."""

from typing import Any

from tests.conftest import MakeClient
from tests.research.test_research_flow import researched


def ids(run: dict[str, Any]) -> dict[str, int]:
    return {a["account"]["name"]: a["account"]["provider_company_id"] for a in run["accounts"]}


def test_case_draft_and_approval_through_api(make_client: MakeClient) -> None:
    client, _ = make_client()
    run = researched(client)
    rid, acc = run["id"], ids(run)

    case = client.get(f"/api/research/{rid}/accounts/{acc['Ledgerloop']}/case").json()
    assert case["recommended_route"] == "cold_email"
    assert all(case[k] for k in ("why_account", "why_person", "why_now", "why_us"))

    r = client.post(f"/api/research/{rid}/accounts/{acc['Ledgerloop']}/drafts")
    assert r.status_code == 201, r.text
    draft = client.get(f"/api/drafts/{r.json()['draft_id']}").json()
    assert draft["status"] == "verified" and draft["sending"] == "disabled"
    assert [a["outcome"] for a in draft["verifier_log"]] == ["pass"]

    bad = client.post(f"/api/drafts/{draft['id']}/approve", json={"expected_hash": "0" * 64})
    assert bad.status_code == 409
    ok = client.post(
        f"/api/drafts/{draft['id']}/approve", json={"expected_hash": draft["content_hash"]}
    )
    assert ok.status_code == 200 and ok.json()["status"] == "approved"


def test_flawed_draft_is_revised_and_rejected_account_refused(make_client: MakeClient) -> None:
    client, _ = make_client()
    run = researched(client)
    rid, acc = run["id"], ids(run)
    r = client.post(f"/api/research/{rid}/accounts/{acc['Quartzdesk']}/drafts")
    draft = client.get(f"/api/drafts/{r.json()['draft_id']}").json()
    assert [a["outcome"] for a in draft["verifier_log"]] == ["fail", "pass"]
    assert draft["verifier_log"][0]["findings"][0]["code"] == "unsupported_number"
    assert "30%" not in draft["body"]

    refused = client.post(f"/api/research/{rid}/accounts/{acc['Orbitly']}/drafts")
    assert refused.status_code == 409
    assert "no_relevant_buyer" in refused.json()["detail"]["message"]


def test_case_and_draft_over_the_api(make_client: MakeClient) -> None:
    client, _ = make_client()
    run = researched(client)
    rid, acc = run["id"], ids(run)
    case = client.get(f"/api/research/{rid}/accounts/{acc['Ledgerloop']}/case").json()
    assert case["why_account"] and case["why_person"] and case["why_now"] and case["why_us"]
    assert case["recommended_route"] == "cold_email" and case["mode"] == "replay"
    made = client.post(f"/api/research/{rid}/accounts/{acc['Quartzdesk']}/drafts").json()
    draft = client.get(f"/api/drafts/{made['draft_id']}").json()
    assert draft["status"] == "verified" and draft["sending"] == "disabled"
    done = client.post(
        f"/api/drafts/{draft['id']}/approve", json={"expected_hash": draft["content_hash"]}
    )
    assert done.status_code == 200 and done.json()["status"] == "approved"
