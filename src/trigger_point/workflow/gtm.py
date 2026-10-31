"""Outcomes, pipeline, learning and finance. Pure functions over stored records.

The arithmetic lives here so it can be tested. Three rules hold throughout: fixture outcomes never
teach anything, pipeline is never revenue, and a number with no valid denominator is shown as
unknown rather than zero."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel

from trigger_point.workflow.strategy import StrategyDraft

MIN_SAMPLE = 5  # below this a group's result is reported as too small to act on
OutcomeKind = Literal[
    "reply",
    "positive_reply",
    "meeting_booked",
    "meeting_held",
    "opportunity_created",
    "closed_won",
    "closed_lost",
    "disqualified",
    "opted_out",
    "bounced",
]
# Furthest-stage order. Loss, disqualification and opt-out end the account whatever came before.
STAGES: tuple[str, ...] = (
    "reply",
    "positive_reply",
    "meeting_booked",
    "meeting_held",
    "opportunity_created",
    "closed_won",
)
ENDED = ("closed_lost", "disqualified", "opted_out", "bounced")
STAGE_CRITERIA = {
    "reply": "They answered",
    "positive_reply": "They showed interest",
    "meeting_booked": "A time is agreed",
    "meeting_held": "The meeting happened",
    "opportunity_created": "A qualified need, buyer and next step exist",
    "closed_won": "They signed",
    "closed_lost": "They said no",
    "disqualified": "They do not fit",
    "opted_out": "They asked to stop",
    "bounced": "The message did not arrive",
}
NEXT_ACTION = {
    "reply": "Answer and qualify",
    "positive_reply": "Propose a meeting",
    "meeting_booked": "Prepare from the case file",
    "meeting_held": "Record what you learned and the next step",
    "opportunity_created": "Agree the next step with the buyer",
}
ADVANCED = ("meeting_held", "opportunity_created", "closed_won")
# A real sender does not exist, so email can only be a draft. Everything else is manual.
DRAFT_ONLY_CHANNELS = {"email"}


class Outcome(BaseModel):
    id: str
    mission_id: str
    account_id: int | None = None
    account_name: str | None = None
    kind: OutcomeKind
    occurred_on: date
    mode: str  # the mission's mode: only `live` may teach
    source: str = "manual"
    signal_type: str | None = None
    persona: str | None = None
    channel: str = "email"
    value: float | None = None
    currency: str | None = None
    reason: str | None = None
    note: str | None = None


def label_strategy(
    draft: StrategyDraft, known_competitors: list[str], proof_points: list[str]
) -> StrategyDraft:
    """Applies what code can check to what the model proposed."""
    known = [k.lower() for k in known_competitors]
    competitors = [
        c.model_copy(
            update={
                "basis": "stated"
                if any(c.name.lower() in k or k in c.name.lower() for k in known)
                else "inferred"
            }
        )
        for c in draft.competitors
    ]
    proof = draft.value_proposition.proof
    needs = list(draft.claims_needing_proof)
    if proof and proof not in proof_points:
        needs.append(proof)
        proof = ""
    channels = [
        c.model_copy(
            update={
                "availability": "draft_only"
                if c.channel.lower() in DRAFT_ONLY_CHANNELS
                else "manual"
            }
        )
        for c in draft.channels
    ]
    return draft.model_copy(
        update={
            "competitors": competitors,
            "value_proposition": draft.value_proposition.model_copy(update={"proof": proof}),
            "claims_needing_proof": needs,
            "channels": channels,
        }
    )


def build_pipeline(outcomes: list[Outcome]) -> dict[str, Any]:
    groups: dict[Any, list[Outcome]] = defaultdict(list)
    for o in outcomes:
        groups[o.account_id or o.account_name].append(o)
    accounts = []
    open_pipeline: dict[str, float] = defaultdict(float)
    won: dict[str, float] = defaultdict(float)
    for rows in groups.values():
        rows = sorted(rows, key=lambda o: o.occurred_on)
        ended = [o for o in rows if o.kind in ENDED]
        reached = [o for o in rows if o.kind in STAGES]
        best = max(reached, key=lambda o: STAGES.index(o.kind), default=None)
        stage = ended[-1].kind if ended else (best.kind if best else rows[-1].kind)
        valued = [o for o in rows if o.value is not None]
        latest = valued[-1] if valued else None
        if latest is not None and latest.currency:
            if stage == "closed_won":
                won[latest.currency] += latest.value or 0
            elif stage == "opportunity_created":
                open_pipeline[latest.currency] += latest.value or 0
        accounts.append(
            {
                "account_id": rows[-1].account_id,
                "account_name": rows[-1].account_name,
                "stage": stage,
                "last_activity": rows[-1].occurred_on.isoformat(),
                "next_action": NEXT_ACTION.get(stage),
                "value": latest.value if latest else None,
                "currency": latest.currency if latest else None,
                "mode": rows[-1].mode,
            }
        )
    counts = {s: sum(1 for a in accounts if a["stage"] == s) for s in (*STAGES, *ENDED)}
    return {
        "accounts": accounts,
        "counts": counts,
        "criteria": STAGE_CRITERIA,
        "open_pipeline": dict(open_pipeline),
        "won_revenue": dict(won),
    }


def propose_changes(outcomes: list[Outcome]) -> dict[str, Any]:
    """Compares signals by how often they led to a meeting or better. It only proposes: a person
    decides, and fixture data is excluded before anything is counted."""
    real = [o for o in outcomes if o.mode == "live"]
    groups: dict[str, list[Outcome]] = defaultdict(list)
    for o in real:
        if o.signal_type:
            groups[o.signal_type].append(o)
    too_small = [k for k, v in groups.items() if len(v) < MIN_SAMPLE]
    proposals = []
    for signal, rows in groups.items():
        if len(rows) < MIN_SAMPLE:
            continue
        wins = [o for o in rows if o.kind in ADVANCED]
        rate = len(wins) / len(rows)
        others = [o for k, v in groups.items() if k != signal for o in v]
        baseline = sum(1 for o in others if o.kind in ADVANCED) / len(others) if others else None
        if baseline is None or rate <= baseline:
            continue
        proposals.append(
            {
                "signal": signal,
                "sample": len(rows),
                "rate": round(rate, 3),
                "baseline": round(baseline, 3),
                "change": f"Give {signal.replace('_', ' ')} more weight in timing",
                "caveat": "Correlation, not causation. Check selection bias and delayed outcomes.",
                "outcome_ids": [o.id for o in rows],
            }
        )
    return {
        "proposals": proposals,
        "too_small": too_small,
        "excluded_fixture": len(outcomes) - len(real),
        "counted": len(real),
        "min_sample": MIN_SAMPLE,
    }


def _per(amount: float, count: int) -> float | None:
    return round(amount / count, 4) if count else None


def finance_metrics(
    usd_actual: float, usd_estimated: float, accounts: int, qualified: int, meetings: int
) -> dict[str, float | None]:
    """Cost per unit on actual spend only. No denominator means unknown, not zero."""
    return {
        "usd_actual": round(usd_actual, 4),
        "usd_estimated": round(usd_estimated, 4),
        "cost_per_account": _per(usd_actual, accounts),
        "cost_per_qualified": _per(usd_actual, qualified),
        "cost_per_meeting": _per(usd_actual, meetings),
    }
