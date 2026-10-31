from datetime import UTC, datetime
from typing import Any

from tests.api.conftest import MakeClient
from trigger_point.context.extractor import ExtractionError, ExtractionResult
from trigger_point.web.crawl import PageRecord
from trigger_point.web.fetcher import FetchResult

GOAL = "Find B2B SaaS companies that are scaling their support teams"


def intake(client: Any, url: str = "supportpilot.example") -> Any:
    return client.post("/api/contexts", json={"website_url": url, "goal": GOAL})


def claims(ctx: dict[str, Any], field: str) -> dict[str, dict[str, Any]]:
    return {c["text"]: c for c in ctx[field]}


def test_unsafe_url_is_rejected_before_any_run(make_client: MakeClient) -> None:
    client, store = make_client()
    r = intake(client, "http://169.254.169.254/latest/meta-data")
    assert r.status_code == 422
    assert r.json()["detail"]["reason"] == "ip_not_public"
    assert store.list_runs() == []


def test_empty_goal_is_rejected(make_client: MakeClient) -> None:
    client, _ = make_client()
    r = client.post("/api/contexts", json={"website_url": "supportpilot.example", "goal": " "})
    assert r.status_code == 422


def test_replay_intake_produces_grounded_reviewable_context(make_client: MakeClient) -> None:
    client, _ = make_client()
    r = intake(client)
    assert r.status_code == 201
    body = r.json()
    assert body["version"] == 1 and body["status"] == "review_required"

    ctx = client.get(f"/api/contexts/{body['context_id']}").json()
    assert ctx["mode"] == "replay"
    assert ctx["website_url"] == "https://supportpilot.example/"
    proof = claims(ctx, "proof_points")
    assert proof["Resolves 90% of tickets automatically."]["status"] == "unsupported"
    assert proof["Ledgerloop cut first-response time from 9 hours to 40 minutes."]["status"] == (
        "supported"
    )
    pains = ctx["customer_pains"]
    assert all(c["kind"] == "inference" and c["status"] == "not_applicable" for c in pains)
    crawled = {p["url"] for p in ctx["pages"]}
    assert "https://supportpilot.example/pricing" in crawled
    assert not any("login" in u for u in crawled)
    assert all(p["retrieved_at"].startswith("2026-10-31") for p in ctx["pages"])


def test_run_receipt_is_explicit_about_mode_and_coverage(make_client: MakeClient) -> None:
    client, _ = make_client()
    run_id = intake(client).json()["run_id"]
    receipt = client.get(f"/api/runs/{run_id}").json()
    assert receipt["mode"] == "replay"
    assert receipt["outcome"] == "completed"
    assert receipt["pages_attempted"] == 5 and receipt["pages_ok"] == 5
    assert receipt["llm_calls"] == []
    assert receipt["provider_modes"] == {"web": "replay", "llm": "replay"}
    assert {"crawl", "extract", "ground"} <= set(receipt["stage_ms"])
    assert receipt["unsupported_claim_count"] == 1


class DeadFetcher:
    def fetch(self, url: str) -> FetchResult:
        return FetchResult(url, url, "timeout", datetime(2026, 10, 31, tzinfo=UTC), error="timeout")


def test_unreachable_site_yields_empty_context_with_visible_gap(make_client: MakeClient) -> None:
    client, _ = make_client(fetcher=DeadFetcher())
    body = intake(client).json()
    ctx = client.get(f"/api/contexts/{body['context_id']}").json()
    assert ctx["value_propositions"] == [] and ctx["company_name"] is None
    assert any("could not retrieve" in u.lower() for u in ctx["unknowns"])
    receipt = client.get(f"/api/runs/{body['run_id']}").json()
    assert receipt["outcome"] == "completed_with_gaps"
    assert receipt["page_failures"][0]["status"] == "timeout"


class BrokenExtractor:
    def extract(self, seed_url: str, goal: str, pages: list[PageRecord]) -> ExtractionResult:
        raise ExtractionError("model stopped with refusal")


def test_extraction_failure_is_recorded_and_surfaced(make_client: MakeClient) -> None:
    client, store = make_client(extractor=BrokenExtractor())
    r = intake(client)
    assert r.status_code == 502
    run = client.get(f"/api/runs/{r.json()['detail']['run_id']}").json()
    assert run["outcome"] == "failed"
    assert "refusal" in run["errors"][0]


def test_edit_then_approve_versions_and_preserves_machine_draft(make_client: MakeClient) -> None:
    client, _ = make_client()
    cid = intake(client).json()["context_id"]
    original = client.get(f"/api/contexts/{cid}").json()
    kept = original["value_propositions"][0]["text"]

    r = client.patch(
        f"/api/contexts/{cid}", json={"set": {"value_propositions": [kept, "Live in one day"]}}
    )
    assert r.status_code == 200 and r.json()["version"] == 2
    edited = claims(client.get(f"/api/contexts/{cid}").json(), "value_propositions")
    assert edited[kept]["kind"] == "fact" and edited[kept]["status"] == "supported"
    assert edited["Live in one day"]["kind"] == "user_provided"
    assert len(edited) == 2

    blocked = client.post(f"/api/contexts/{cid}/approve", json={})
    assert blocked.status_code == 409
    assert "Resolves 90% of tickets automatically." in blocked.json()["detail"]["unsupported"]

    ok = client.post(f"/api/contexts/{cid}/approve", json={"acknowledge_unsupported": True})
    assert ok.status_code == 200 and ok.json()["version"] == 3
    approved = client.get(f"/api/contexts/{cid}").json()
    assert approved["status"] == "approved" and approved["approved_at"]
    assert "Resolves 90% of tickets automatically." not in claims(approved, "proof_points")

    v1 = client.get(f"/api/contexts/{cid}", params={"version": 1}).json()
    assert "Resolves 90% of tickets automatically." in claims(v1, "proof_points")
    assert [v["version"] for v in client.get(f"/api/contexts/{cid}/versions").json()] == [1, 2, 3]


def test_edit_after_approval_requires_new_review(make_client: MakeClient) -> None:
    client, _ = make_client()
    cid = intake(client).json()["context_id"]
    client.post(f"/api/contexts/{cid}/approve", json={"acknowledge_unsupported": True})
    r = client.patch(f"/api/contexts/{cid}", json={"set": {"exclusions": ["Agencies"]}})
    assert r.json()["status"] == "review_required"


def test_edit_rejects_unknown_field(make_client: MakeClient) -> None:
    client, _ = make_client()
    cid = intake(client).json()["context_id"]
    assert client.patch(f"/api/contexts/{cid}", json={"set": {"pages": ["x"]}}).status_code == 422


def test_missing_context_is_404(make_client: MakeClient) -> None:
    client, _ = make_client()
    assert client.get("/api/contexts/nope").status_code == 404
    assert client.get("/api/runs/nope").status_code == 404


class TitleFetcher:
    def fetch(self, url: str) -> FetchResult:
        html = (
            "<html><head><title>Acme Robotics | Warehouse picking robots</title></head>"
            "<body><p>We build robots.</p></body></html>"
        )
        return FetchResult(
            url, url, "ok", datetime(2026, 10, 31, tzinfo=UTC), 200, "text/html", html, "h"
        )


class TitleQuotingExtractor:
    def extract(self, seed_url: str, goal: str, pages: list[PageRecord]) -> ExtractionResult:
        from trigger_point.models.context import ContextClaim, ContextDraft

        claim = ContextClaim(
            text="Acme Robotics",
            kind="fact",
            source_url=seed_url,
            excerpt="Acme Robotics | Warehouse picking robots",
            confidence="high",
        )
        return ExtractionResult(ContextDraft(company_name=claim), None, "replay")


def test_quotes_from_the_page_title_are_grounded(make_client: MakeClient) -> None:
    client, _ = make_client(fetcher=TitleFetcher(), extractor=TitleQuotingExtractor())
    cid = intake(client, "acme.example").json()["context_id"]
    ctx = client.get(f"/api/contexts/{cid}").json()
    assert ctx["company_name"]["status"] == "supported"
