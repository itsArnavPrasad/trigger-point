"""Regenerate the synthetic Crustdata replay fixtures for the SupportPilot demo mission.

The companies and people are fictional (reserved .example domains) and every file is labelled
"synthetic demo fixture". Responses follow the documented 2025-11-01 shapes. Re-run this after
changing the mission compiler or research request compilers: replay requests are matched by
exact request hash. Job and person fixtures are produced by running the real pipeline against a
synthetic responder and recording exactly what it asks for.

    uv run python scripts/make_replay_fixtures.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import httpx

from trigger_point.mission.compiler import compile_plan, compile_search_request, relaxation_steps
from trigger_point.mission.models import MissionDraft
from trigger_point.providers.crustdata.client import request_key

ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "replay"
CRUST = ROOT / "crustdata"
SOURCE = "synthetic demo fixture (fictional companies, documented response shape)"
SELLER = "supportpilot.example"


def write(
    endpoint: str,
    method: str,
    body: Any,
    params: dict[str, str] | None,
    status: int,
    payload: Any,
    credits: str,
) -> None:
    key = request_key(method, endpoint, body, params)
    target = CRUST / endpoint.strip("/").replace("/", "_") / f"{key[:16]}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "_source": SOURCE,
                "_request": {"method": method, "path": endpoint, "body": body, "params": params},
                "status": status,
                "headers": {"x-credits-used": credits},
                "body": payload,
            },
            indent=2,
        )
        + "\n"
    )


def company(
    cid: int,
    name: str,
    domain: str,
    size: str,
    total: int,
    g6: float,
    g12: float,
    openings: int,
    country: str = "USA",
    updated: str = "2026-10-21T00:00:00Z",
    showcase: bool = False,
) -> dict[str, Any]:
    kind = "showcase" if showcase else "company"
    return {
        "crustdata_company_id": cid,
        "basic_info": {
            "name": name,
            "primary_domain": domain,
            "all_domains": [domain],
            "website": f"https://{domain}",
            "professional_network_url": f"https://www.linkedin.example/{kind}/{cid}",
            "employee_count_range": size,
            "industries": ["Software Development"],
            "description": None,
        },
        "headcount": {
            "total": total,
            "growth_percent": {
                "1m": round(g6 / 6, 1),
                "3m": round(g6 / 2, 1),
                "6m": g6,
                "12m": g12,
            },
        },
        "hiring": {"openings_count": openings},
        "locations": {"country": country, "headquarters": None},
        "updated_at": updated,
    }


COMPANIES = [
    company(1001, "Ledgerloop", "ledgerloop.example", "201-500", 340, 14.2, 31.0, 12),
    company(1002, "Quartzdesk", "quartzdesk.example", "51-200", 120, 22.5, 40.1, 9),
    company(
        1003, "Brightlane HR", "brightlane.example", "501-1000", 720, 3.1, 8.4, 4, country="CAN"
    ),
    company(
        1004,
        "Fernwood Billing",
        "fernwood.example",
        "201-500",
        260,
        -2.0,
        1.5,
        0,
        updated="2026-06-05T00:00:00Z",
    ),
    company(1005, "SupportPilot", SELLER, "51-200", 85, 10.0, 25.0, 3),
    company(
        1101,
        "Ledgerloop Engineering",
        "ledgerloop.example",
        "51-200",
        60,
        5.0,
        9.0,
        2,
        showcase=True,
    ),
    company(1006, "Orbitly", "orbitly.example", "51-200", 150, 18.0, 35.0, 15, country="CAN"),
]


REFERENCE_DATE = "2026-10-31"
GOAL = "Book meetings with B2B SaaS companies that are scaling their support teams"


def _job(jid: int, cid: int, title: str, posted: str, desc: str) -> dict[str, Any]:
    return {
        "crustdata_job_id": jid,
        "job_details": {
            "title": title,
            "category": "Customer Service",
            "url": f"https://jobs.example/postings/{jid}",
        },
        "company": {"basic_info": {"crustdata_company_id": cid}},
        "metadata": {"date_added": f"{posted}T00:00:00", "date_updated": "2026-10-29T00:00:00"},
        "content": {"description": desc},
    }


def _person(pid: int, cid: int, name: str, title: str, start: str) -> dict[str, Any]:
    return {
        "crustdata_person_id": pid,
        "basic_profile": {"name": name, "current_title": title},
        "experience": {
            "employment_details": {
                "current": [{"title": title, "crustdata_company_id": cid, "start_date": start}]
            }
        },
        "social_handles": {
            "professional_network_identifier": {"profile_url": f"https://profiles.example/{pid}"}
        },
        "metadata": {"updated_at": "2026-10-18T00:00:00Z"},
    }


SYNTH_JOBS = [
    _job(
        7001,
        1001,
        "Customer Support Specialist",
        "2026-10-24",
        "Join our support team. You will resolve 60+ tickets a day in Zendesk and help us "
        "build macros for common billing questions.",
    ),
    _job(
        7002,
        1001,
        "Support Operations Lead",
        "2026-10-17",
        "Own our helpdesk configuration and reporting.",
    ),
    _job(
        7003,
        1002,
        "Customer Success Manager",
        "2026-10-28",
        "Work with customers in Intercom to drive adoption.",
    ),
]
SYNTH_PEOPLE = [
    _person(8001, 1001, "Maya Example", "Head of Support", "2025-03-01"),
    _person(8002, 1001, "Leo Example", "Customer Support Specialist", "2026-01-10"),
    _person(8003, 1002, "Priya Example", "Director, Customer Support", "2024-07-01"),
    _person(8004, 1003, "Sam Example", "VP Customer Experience", "2023-11-01"),
    # Profile still lists Orbitly, but the current employer id is another company: stale.
    _person(8005, 4242, "Noah Example", "Head of Support", "2026-09-01"),
]


class SyntheticResponder(httpx.BaseTransport):
    """Answers job/person searches from the synthetic tables, filtered by the requested
    company ids."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        ids = set(body["filters"]["conditions"][0]["value"])
        if request.url.path == "/job/search":
            rows = [
                j for j in SYNTH_JOBS if j["company"]["basic_info"]["crustdata_company_id"] in ids
            ]
            payload: dict[str, Any] = {
                "job_listings": rows,
                "next_cursor": None,
                "total_count": len(rows),
            }
            credits = 0.03 * len(rows)
        else:
            orbitly = {1006} & ids
            rows = [
                p
                for p in SYNTH_PEOPLE
                if p["experience"]["employment_details"]["current"][0]["crustdata_company_id"]
                in ids
                or (orbitly and p["crustdata_person_id"] == 8005)
            ]
            payload = {"profiles": rows, "next_cursor": None, "total_count": len(rows)}
            credits = 0.23 * len(rows)
        return httpx.Response(200, json=payload, headers={"x-credits-used": str(round(credits, 2))})


DRAFT_SOURCE = (
    "hand-authored replay fixture (template-filled from the case evidence; not a model response)"
)


def _draft_wire(case: Any, invent_number: bool = False) -> dict[str, Any]:
    hooks = [e for e in case.evidence if e.id in case.hook_evidence_ids]
    hook = next((e for e in hooks if e.source_kind == "job_posting"), hooks[0])
    proof = next(e for e in case.evidence if e.id in case.seller_evidence_ids and "45%" in e.claim)
    first = (case.recipient.person.name or "there").split()[0]
    if hook.source_kind == "job_posting":
        when = f" on {hook.event_on.isoformat()}" if hook.event_on else ""
        opener = f"{case.account_name} posted a {hook.excerpt} role{when}."
    else:
        opener = hook.claim.replace(" (", ", ", 1).rstrip(").") + "."
    metric = "cuts handle time by 30% and" if invent_number else ""
    body = (
        f"Hi {first},\n\n{opener} Teams growing support often start by taking repetitive "
        f"tickets off the queue. SupportPilot {metric} automatically resolves up to 45% of inbound "
        "tickets for teams handling more than 5,000 tickets per month. Would a short call next "
        "week be useful?\n\n[Your name]"
    ).replace("  ", " ")
    return {
        "_source": DRAFT_SOURCE,
        "subject": f"Support hiring at {case.account_name}",
        "body": body,
        "hook_evidence_id": hook.id,
        "proof_point_evidence_id": proof.id,
        "claims": [
            {"text": opener, "kind": "fact", "evidence_ids": [hook.id]},
            {
                "text": "Teams growing support often start with repetitive tickets",
                "kind": "inference",
                "evidence_ids": [],
            },
            {
                "text": "Resolves up to 45% of inbound tickets above 5,000 tickets per month",
                "kind": "fact",
                "evidence_ids": [proof.id],
            },
        ],
        "follow_ups": [
            {
                "day_offset": 4,
                "angle": "How answers link back to the help-center article",
                "evidence_ids": [e for e in case.seller_evidence_ids if e != proof.id][:1],
            },
        ],
    }


def write_draft_fixtures(services: Any, research: Any) -> None:
    for task in ("first_touch_draft", "first_touch_revision"):
        for old in (ROOT / "llm" / task).glob("*.json") if (ROOT / "llm" / task).exists() else []:
            old.unlink()
    for a in research.accounts:
        case = services.cases.get_or_build(research.id, a.account.provider_company_id)
        if case.recommended_route != "cold_email":
            continue
        key = f"{case.account_domain}__{case.account_id}"
        flawed = case.account_name == "Quartzdesk"  # demo: verifier forces one revision
        first = _draft_wire(case, invent_number=flawed)
        for task, wire in (
            ("first_touch_draft", first),
            *((("first_touch_revision", _draft_wire(case)),) if flawed else ()),
        ):
            target = ROOT / "llm" / task / f"{key}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(wire, indent=2) + "\n")
        print(f"  draft fixture for {case.account_name}{' (flawed first draft)' if flawed else ''}")


def record_research_fixtures() -> None:
    from trigger_point.api.app import AppDeps, build_services
    from trigger_point.config import load_settings
    from trigger_point.context.extractor import LlmContextExtractor
    from trigger_point.llm.replay import ReplayStructuredLlm
    from trigger_point.providers.crustdata.client import CreditBudget, CrustdataClient
    from trigger_point.providers.crustdata.replay import RecordingTransport, ReplayTransport
    from trigger_point.store.db import Store
    from trigger_point.web.fetcher import FixtureFetcher

    (CRUST / "_meta.json").write_text(
        json.dumps(
            {
                "reference_date": REFERENCE_DATE,
                "note": "Replay research is evaluated as of this date so freshness cannot drift.",
            },
            indent=2,
        )
        + "\n"
    )
    recorder = RecordingTransport(SyntheticResponder(), CRUST, source_label=SOURCE)
    replay = ReplayTransport(CRUST)

    class Router(httpx.BaseTransport):
        """Only job/person requests are synthesised and recorded; the rest replays as-is."""

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            if request.url.path in ("/job/search", "/person/search"):
                return recorder.handle_request(request)
            return replay.handle_request(request)

    transport = Router()

    def factory(budget: CreditBudget) -> CrustdataClient:
        return CrustdataClient(
            httpx.Client(transport=transport), "synthetic", budget, mode="replay"
        )

    with tempfile.TemporaryDirectory() as tmp:
        settings = load_settings({"DATABASE_URL": f"sqlite:///{tmp}/gen.db"})
        llm = ReplayStructuredLlm(ROOT / "llm")
        services = build_services(
            settings,
            AppDeps(
                FixtureFetcher(ROOT / "sites"),
                LlmContextExtractor(llm),
                Store(f"{tmp}/gen.db"),
                llm,
                factory,
            ),
        )
        out = services.contexts.intake(SELLER, GOAL)
        services.contexts.approve(out.context_id, "fixture-script", acknowledge_unsupported=True)
        mission = services.missions.compile(out.context_id)
        services.missions.approve(mission.id)
        discovery = services.discovery.run(mission.id)
        research = services.research.run(discovery.id)
        for a in research.accounts:
            print(
                f"  {a.account.name:<24} {a.score.status:<22} {a.score.total:6.2f} "
                f"{','.join(a.score.rejections)}"
            )
        write_draft_fixtures(services, research)


def main() -> None:
    raw = json.loads((ROOT / "llm" / "mission_compile" / f"{SELLER}.json").read_text())
    draft = MissionDraft.model_validate({k: v for k, v in raw.items() if not k.startswith("_")})
    plan = compile_plan(draft, seller_domain=SELLER, credit_budget=5.0)
    request = compile_search_request(plan)

    write(
        "/account/endpoints",
        "GET",
        None,
        {"path": "/company/search"},
        200,
        {
            "api_version": "2025-11-01",
            "token_limit_rpm": None,
            "endpoints": [
                {
                    "path": "/company/search",
                    "category": "Company",
                    "status": "enabled",
                    "effective_rate_limit_rpm": 30,
                    "fields": {"enabled": [], "disabled": []},
                    "base_credits": 0.03,
                }
            ],
        },
        "0",
    )
    seller_basic = company(1005, "SupportPilot", SELLER, "51-200", 85, 10.0, 25.0, 3)["basic_info"]
    write(
        "/company/identify",
        "POST",
        {"domains": [SELLER], "exact_match": True},
        None,
        200,
        [
            {
                "matched_on": SELLER,
                "match_type": "domain",
                "matches": [
                    {
                        "confidence_score": 1,
                        "company_data": {"crustdata_company_id": 1005, "basic_info": seller_basic},
                    }
                ],
            }
        ],
        "0",
    )
    n = len(COMPANIES)
    write(
        "/company/search",
        "POST",
        request.to_body(),
        None,
        200,
        {"companies": COMPANIES, "next_cursor": None, "total_count": None},
        str(round(0.43 * n, 2)),
    )
    for step in relaxation_steps(plan):  # relaxed variants return the same synthetic page
        write(
            "/company/search",
            "POST",
            compile_search_request(step.plan).to_body(),
            None,
            200,
            {"companies": COMPANIES, "next_cursor": None, "total_count": None},
            str(round(0.43 * n, 2)),
        )
    print(f"wrote discovery fixtures; search limit {request.limit}; recording research run:")
    record_research_fixtures()


if __name__ == "__main__":
    main()
