"""Evaluation set for the rules code owns. `uv run python -m evals.run_evals` prints a scorecard.

Each case is known-good, edge, contradictory, stale or empty, as the spec asks. These measure the
deterministic checks. Model quality needs labelled live output and is listed in the audit."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from tests.research.factories import company, plan
from trigger_point.context.grounding import ground_context
from trigger_point.mission.selection import select_accounts
from trigger_point.models.context import BusinessContext, ContextClaim
from trigger_point.models.evidence import Evidence
from trigger_point.office.views import stakeholder_role
from trigger_point.workflow.gtm import MIN_SAMPLE, Outcome, finance_metrics
from trigger_point.workflow.loop import MATURITY_DAYS, Touch, compare, measure, quote_found
from trigger_point.workflow.outreach import OutreachWire, verify_outreach
from trigger_point.workflow.verification import audit_evidence

NOW = datetime(2026, 10, 31, tzinfo=UTC)
TODAY = date(2026, 10, 31)
Case = tuple[str, str, Callable[[], bool]]


def _claim(text: str, excerpt: str) -> bool:
    ctx = BusinessContext(
        website_url="https://s.example/",
        domain="s.example",
        user_goal="g",
        mode="replay",
        run_id="r",
        product_summary=[
            ContextClaim(
                text=text,
                kind="fact",
                source_url="https://s.example/",
                excerpt=excerpt,
                confidence="high",
            )
        ],
    )
    page = {"https://s.example/": "We resolve tickets inside your helpdesk every single day."}
    return ground_context(ctx, page).product_summary[0].status == "supported"


def _evidence(**over: Any) -> str:
    base: dict[str, Any] = {
        "id": "e",
        "entity_type": "account",
        "entity_id": "1",
        "claim": "c",
        "source_kind": "job_posting",
        "source_url": "https://j.example/1",
        "event_on": date(2026, 10, 21),
        "retrieved_at": NOW,
        "excerpt": "x",
    }
    return audit_evidence(Evidence.model_validate({**base, **over}), "1", TODAY, NOW).status


def _msg(body: str, notes: str = "") -> bool:
    wire = OutreachWire(subject="Hello", body=body, claims=[])
    return not [
        f
        for f in verify_outreach(wire, ["First topic free"], "School", notes)
        if f.severity == "error"
    ]


def _dupes() -> int:
    kept, _ = select_accounts(
        [company(1), company(1), company(2, primary_domain="b.example")], plan(), "s.example", None
    )
    return len(kept)


def _touches(n: int, mode: str = "live", days_ago: int = MATURITY_DAYS + 1) -> list[Touch]:
    sent_on = TODAY - timedelta(days=days_ago)
    return [
        Touch(id=f"{a}{i}", audience=a, sent_on=sent_on, mode=mode)
        for a in ("school", "parent")
        for i in range(n)
    ]


def _report(touches: list[Touch], wins: int = 0) -> dict[str, Any]:
    outcomes = [
        _outcome(i, "meeting_booked").model_copy(update={"outreach_id": touches[i].id})
        for i in range(wins)
    ]
    return compare(touches, outcomes, TODAY, ("live",))


def _outcome(i: int, kind: str = "meeting_held", mode: str = "live") -> Outcome:
    return Outcome.model_validate(
        {
            "id": str(i),
            "mission_id": "m",
            "account_id": i,
            "kind": kind,
            "occurred_on": "2026-10-02",
            "mode": mode,
            "signal_type": "active_hiring",
        }
    )


SUITES: dict[str, list[Case]] = {
    "unsupported_claim_rejection": [
        (
            "known-good",
            "quote on the page",
            lambda: _claim("Works in helpdesks", "resolve tickets inside your helpdesk"),
        ),
        (
            "contradictory",
            "quote not on the page",
            lambda: not _claim("Replaces helpdesks", "replaces your helpdesk entirely"),
        ),
    ],
    "source_and_event_dates": [
        ("known-good", "fresh and sourced", lambda: _evidence() == "verified"),
        ("stale", "older than policy", lambda: _evidence(event_on=date(2026, 1, 2)) == "stale"),
        ("empty", "no date", lambda: _evidence(event_on=None) == "undated"),
        ("edge", "future date", lambda: _evidence(event_on=date(2027, 1, 1)) == "unverifiable"),
        ("contradictory", "wrong entity", lambda: _evidence(entity_id="9") == "entity_mismatch"),
    ],
    "duplicate_accounts": [
        ("edge", "same id twice is one account", lambda: _dupes() < 3),
        ("known-good", "distinct companies kept", lambda: _dupes() == 2),
    ],
    "stakeholder_roles": [
        (
            "known-good",
            "head of function",
            lambda: stakeholder_role("Head of Support") == "Functional owner",
        ),
        ("edge", "no title", lambda: stakeholder_role(None) == "End user or practitioner"),
    ],
    "factual_personalization": [
        ("known-good", "plain message", lambda: _msg("Your first topic is free. Could we talk?")),
        ("contradictory", "invented result", lambda: not _msg("Marks rose 40% for students.")),
        (
            "edge",
            "number from the user's notes",
            lambda: _msg("For your 1200 students.", "1200 students"),
        ),
        ("edge", "fake familiarity", lambda: not _msg("I noticed your school is growing.")),
        ("empty", "blank body", lambda: not _msg("")),
        ("contradictory", "invented pilot", lambda: not _msg("We are currently running a pilot.")),
        ("known-good", "proposing a pilot", lambda: _msg("Could we discuss a small pilot?")),
    ],
    "learning_recommendations": [
        ("empty", "no sends", lambda: _report([])["proposals"] == []),
        ("edge", "small sample", lambda: _report(_touches(MIN_SAMPLE - 1))["proposals"] == []),
        (
            "known-good",
            "a better audience is proposed",
            lambda: _report(_touches(MIN_SAMPLE), wins=3)["proposals"][0]["value"] == "school",
        ),
        (
            "contradictory",
            "fixture never teaches",
            lambda: _report(_touches(50, "replay"))["excluded"] == 100,
        ),
        (
            "edge",
            "a recent send is pending, not a failure",
            lambda: _report(_touches(3, days_ago=1))["pending"] == 6,
        ),
        ("stale", "a small result says wait", lambda: measure(0.9, 2, 0.1, 50)["action"] == "wait"),
        (
            "known-good",
            "a worse result advises rollback",
            lambda: measure(0.1, 9, 0.5, 9)["action"] == "roll_back",
        ),
    ],
    "meeting_insights": [
        (
            "known-good",
            "quote in the source",
            lambda: quote_found("fees are high", "Fees  are\nhigh."),
        ),
        (
            "contradictory",
            "changed wording",
            lambda: not quote_found("fees are low", "fees are high"),
        ),
        ("empty", "blank quote", lambda: not quote_found(" ", "fees are high")),
    ],
    "finance_calculations": [
        (
            "known-good",
            "cost per account",
            lambda: finance_metrics(10, 0, 5, 1, 1)["cost_per_account"] == 2.0,
        ),
        (
            "empty",
            "no denominator is unknown",
            lambda: finance_metrics(10, 0, 0, 0, 0)["cost_per_meeting"] is None,
        ),
    ],
}


def run_all() -> list[dict[str, Any]]:
    return [
        {"suite": suite, "kind": kind, "name": name, "passed": check()}
        for suite, cases in SUITES.items()
        for kind, name, check in cases
    ]


if __name__ == "__main__":
    results = run_all()
    for suite in SUITES:
        rows = [r for r in results if r["suite"] == suite]
        print(f"{suite}: {sum(r['passed'] for r in rows)}/{len(rows)}")
    print(f"total: {sum(r['passed'] for r in results)}/{len(results)}")
