import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.research.factories import NOW, company, plan
from trigger_point.mission.models import Mission
from trigger_point.mission.service import DiscoveryRun
from trigger_point.providers.crustdata.client import CreditBudget, CrustdataClient
from trigger_point.research.service import ResearchFailed, ResearchService
from trigger_point.store.db import Store

REF = date(2026, 10, 31)


def job(jid: int, cid: int, title: str, posted: str, desc: str = "") -> dict[str, Any]:
    return {
        "crustdata_job_id": jid,
        "job_details": {"title": title, "url": f"https://jobs.example/{jid}"},
        "company": {"basic_info": {"crustdata_company_id": cid}},
        "metadata": {"date_added": posted, "date_updated": "2026-10-29T00:00:00"},
        "content": {"description": desc},
    }


def prof(pid: int, cid: int, title: str) -> dict[str, Any]:
    return {
        "crustdata_person_id": pid,
        "basic_profile": {"name": f"Person {pid}", "current_title": title},
        "experience": {
            "employment_details": {"current": [{"title": title, "crustdata_company_id": cid}]}
        },
    }


class Responder:
    def __init__(self, jobs: Any = None, people: Any = None, job_status: int = 200) -> None:
        self.jobs = (
            jobs
            if jobs is not None
            else [
                job(
                    1,
                    1001,
                    "Customer Support Specialist",
                    "2026-10-23T00:00:00",
                    "Uses Zendesk daily",
                )
            ]
        )
        self.people = people if people is not None else [prof(11, 1001, "Head of Support")]
        self.job_status = job_status
        self.requests: list[tuple[str, Any]] = []

    def __call__(self, r: httpx.Request) -> httpx.Response:
        body = json.loads(r.content) if r.content else None
        self.requests.append((r.url.path, body))
        if r.url.path == "/job/search":
            if self.job_status != 200:
                return httpx.Response(
                    self.job_status,
                    json={
                        "error": {
                            "type": "permission_error",
                            "message": "no access",
                            "metadata": [],
                        }
                    },
                )
            return httpx.Response(
                200, json={"job_listings": self.jobs}, headers={"x-credits-used": "0.03"}
            )
        if r.url.path == "/person/search":
            return httpx.Response(
                200, json={"profiles": self.people}, headers={"x-credits-used": "0.23"}
            )
        return httpx.Response(404, json={})


def setup(
    tmp_path: Path, responder: Responder, budget: float = 5.0, accounts: list[Any] | None = None
) -> tuple[ResearchService, str, Store]:
    store = Store(tmp_path / "r.db")
    mission = Mission(
        id="m1",
        context_id="c1",
        context_version=2,
        user_goal="g",
        plan=plan(),
        search_request={},
        estimated_credits="0",
        status="approved",
        mode="replay",
        llm_mode="replay",
        created_at=NOW,
    )
    store.save_mission(mission)
    accounts = accounts or [
        company(1001),
        company(
            1004,
            name="Fernwood",
            primary_domain="fernwood.example",
            headcount_growth_6m_pct=-2.0,
            hiring_openings=0,
        ),
    ]
    store.save_discovery(
        DiscoveryRun(
            id="d1",
            mission_id="m1",
            mode="replay",
            started_at=NOW,
            outcome="completed",
            accounts=accounts,
        )
    )
    http = httpx.Client(transport=httpx.MockTransport(responder))

    def factory(b: CreditBudget) -> CrustdataClient:
        return CrustdataClient(http, "k", b, mode="replay")

    svc = ResearchService(
        store,
        factory,
        budget=budget,
        reference_date=lambda: REF,
        clock=lambda: datetime(2026, 10, 31, tzinfo=UTC),
    )
    return svc, "d1", store


def test_research_ranks_scores_and_explains(tmp_path: Path) -> None:
    responder = Responder()
    svc, did, store = setup(tmp_path, responder)
    run = svc.run(did)
    assert run.outcome == "completed" and run.reference_date == REF
    by_id = {a.account.provider_company_id: a for a in run.accounts}
    ledger, fern = by_id[1001], by_id[1004]
    assert ledger.score.status == "qualified" and ledger.best_person is not None
    assert ledger.best_person.person.name == "Person 11"
    assert any(s.type == "support_team_growth" and s.status == "active" for s in ledger.signals)
    assert any("Zendesk" in e.claim for e in ledger.evidence)
    assert fern.score.status == "rejected" and "no_fresh_why_now" in fern.score.rejections
    assert run.accounts[0].account.provider_company_id == 1001  # ranked
    people_req = next(b for p, b in responder.requests if p == "/person/search")
    ids = people_req["filters"]["conditions"][0]["value"]
    assert ids == [1001]  # rejected accounts are not people-searched
    assert store.get_research(run.id) is not None
    assert [c.endpoint for c in run.calls] == ["/job/search", "/person/search"]


def test_budget_too_small_for_people_leaves_reachability_unknown(tmp_path: Path) -> None:
    # Job search (est. 0.24) fits; actual 0.03 leaves 0.22, below one person result (0.23).
    svc, did, _ = setup(tmp_path, Responder(), budget=0.25)
    run = svc.run(did)
    ledger = next(a for a in run.accounts if a.account.provider_company_id == 1001)
    assert ledger.people_searched is False
    assert ledger.score.status == "insufficient_evidence"
    assert "no_relevant_buyer" not in ledger.score.rejections
    assert any("people search skipped" in n for n in run.notes)


def test_job_search_permission_denied_degrades_to_metric_signals(tmp_path: Path) -> None:
    svc, did, _ = setup(tmp_path, Responder(job_status=403))
    run = svc.run(did)
    assert run.outcome == "completed"
    assert any("job search unavailable" in n for n in run.notes)
    ledger = next(a for a in run.accounts if a.account.provider_company_id == 1001)
    assert {s.type for s in ledger.signals} <= {"headcount_growth", "active_hiring"}


def test_stale_employer_means_no_relevant_buyer(tmp_path: Path) -> None:
    svc, did, _ = setup(tmp_path, Responder(people=[prof(12, 9999, "Head of Support")]))
    run = svc.run(did)
    ledger = next(a for a in run.accounts if a.account.provider_company_id == 1001)
    assert "no_relevant_buyer" in ledger.score.rejections
    assert ledger.people_rejected[0].reason == "current_employer_mismatch"


def test_provider_auth_failure_fails_the_run_visibly(tmp_path: Path) -> None:
    def auth(r: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Invalid API key in request"})

    svc, did, store = setup(tmp_path, Responder())
    svc._factory = lambda b: CrustdataClient(
        httpx.Client(transport=httpx.MockTransport(auth)), "k", b, mode="replay"
    )
    with pytest.raises(ResearchFailed) as exc:
        svc.run(did)
    saved = store.get_research(exc.value.research_id)
    assert saved is not None and saved.outcome == "failed" and "auth" in saved.errors[0]


def test_signals_stage_makes_no_people_call_and_leaves_reachability_unknown(
    tmp_path: Path,
) -> None:
    responder = Responder()
    svc, did, store = setup(tmp_path, responder)
    run = svc.run_signals(did)
    assert run.stage == "signals"
    assert [path for path, _ in responder.requests] == ["/job/search"]
    assert all(not a.people_searched and a.best_person is None for a in run.accounts)
    assert all(not a.score.components["reachability"].known for a in run.accounts)
    assert store.get_research(run.id) is not None


def test_people_stage_finishes_the_run_it_was_given(tmp_path: Path) -> None:
    responder = Responder()
    svc, did, _ = setup(tmp_path, responder)
    first = svc.run_signals(did)
    run = svc.run_people(first.id)
    assert run.id == first.id and run.stage == "people"
    assert [path for path, _ in responder.requests] == ["/job/search", "/person/search"]
    best = run.accounts[0]
    assert best.best_person is not None
    assert best.score.components["reachability"].known
    assert any(e.source_kind == "provider_profile" for e in best.evidence)


def test_people_stage_rerun_does_not_call_the_provider_twice(tmp_path: Path) -> None:
    responder = Responder()
    svc, did, _ = setup(tmp_path, responder)
    run = svc.run_signals(did)
    svc.run_people(run.id)
    again = svc.run_people(run.id)
    assert again.stage == "people"
    assert [path for path, _ in responder.requests].count("/person/search") == 1


def test_people_stage_spends_only_what_the_signals_stage_left(tmp_path: Path) -> None:
    # A fresh 0.25 budget would afford one 0.23 person; after the 0.03 job search only 0.22 is left
    responder = Responder()
    svc, did, _ = setup(tmp_path, responder, budget=0.25)
    run = svc.run_signals(did)
    assert run.credits["actual"] == "0.03"
    finished = svc.run_people(run.id)
    assert "/person/search" not in [path for path, _ in responder.requests]
    assert finished.credits["actual"] == "0.03" and finished.credits["budget"] == "0.25"
    assert any("people search skipped" in n for n in finished.notes)
