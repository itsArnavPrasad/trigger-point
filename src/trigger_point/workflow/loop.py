"""The learning loop's rules. Pure functions over stored records, so each rule can be tested.

Provider data arrives as raw tool responses captured by a hook, and is parsed here by code. A
model never retypes what a customer said: a quote counts only if it is found in the raw source.
A send is the denominator, a test or fixture send never counts, and a result too small or too
recent is reported as that rather than as a finding."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel

from trigger_point.workflow.gtm import ADVANCED, MIN_SAMPLE, Outcome

MATURITY_DAYS = 7  # a younger send has had no fair chance of a result
HOLDOUT_SHARE = 5  # one target in this many keeps the old approach, as the comparison group
MIN_EFFECT = 0.05  # a smaller gap in rate is not called a change
WINS = ("meeting_booked", *ADVANCED)
MAX_SOURCE_CHARS = 400_000
InsightKind = Literal[
    "pain",
    "desired_outcome",
    "objection",
    "alternative",
    "budget",
    "urgency",
    "buying_process",
    "success_criteria",
    "commitment",
    "next_step",
]
ReplyKind = Literal["reply", "opted_out", "bounced"]

_CUT = re.compile(
    r"\s*\(\.\.\.truncated, \d+ chars remaining; continue with [^)]*start_char=(\d+)\.\.\.\)\s*$"
)
_BOUNCE_SENDER = re.compile(r"mailer-daemon|postmaster", re.I)
_OPT_OUT = re.compile(
    r"\bunsubscribe\b|\bstop (emailing|contacting|sending|messaging)\b|"
    r"\bremove me\b|\bdo not (contact|email)\b|\bdon'?t (contact|email)\b|\bopt(ing)?[- ]out\b",
    re.I,
)
# What each kind of comparison would change, if a person agrees.
TARGETS = {
    "audience": "icp",
    "signal_type": "qualification",
    "channel": "channel",
    "strategy_version": "messaging",
    "weekday": "channel",
}
CHANGE_TEXT = {
    "audience": "Put more effort into the {value} audience",
    "signal_type": "Give {value} more weight in timing",
    "channel": "Put more effort into {value}",
    "strategy_version": "Keep the messaging from strategy version {value}",
    "weekday": "Send on {value}",
}


class Message(BaseModel):
    id: str
    thread_id: str | None = None
    sender: str = ""
    subject: str = ""
    body: str = ""
    ours: bool
    received_on: date | None = None


class RawMeeting(BaseModel):
    source_id: str
    title: str
    held_on: date | None = None
    attendees: list[str] = []
    summary: str = ""
    notes: str = ""
    transcript: str = ""
    link: str | None = None

    @property
    def text(self) -> str:
        return f"{self.transcript}\n{self.notes}\n{self.summary}"


class Touch(BaseModel):
    """One message that really left, or that a person says they sent."""

    id: str
    account_name: str | None = None
    audience: str | None = None
    channel: str = "email"
    signal_type: str | None = None
    variant: str = "none"
    strategy_version: int | None = None
    sent_on: date
    mode: str

    @property
    def weekday(self) -> str:
        return self.sent_on.strftime("%A")


def unwrap_tool_response(response: Any) -> dict[str, Any] | None:
    """Claude Code hands a hook the MCP result in one of a few wrappers."""
    if isinstance(response, dict) and "content" not in response:
        return response
    if isinstance(response, dict):
        response = response["content"]
    if isinstance(response, list):
        response = "".join(
            str(p.get("text", "")) for p in response if isinstance(p, dict) and "text" in p
        )
    if not isinstance(response, str):
        return None
    try:
        parsed = json.loads(response)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _day(value: Any) -> date | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def parse_gmail_messages(payload: dict[str, Any]) -> list[Message]:
    listed = payload.get("messages")
    found = []
    for m in listed if isinstance(listed, list) else [payload]:
        if not isinstance(m, dict) or not m.get("id"):
            continue
        found.append(
            Message(
                id=str(m["id"]),
                thread_id=m.get("threadId"),
                sender=str(m.get("sender") or ""),
                subject=str(m.get("subject") or ""),
                body=str(m.get("plaintextBody") or m.get("snippet") or ""),
                ours="SENT" in (m.get("labelIds") or []),
                received_on=_day(m.get("date")),
            )
        )
    return found


def parse_meeting(payload: dict[str, Any]) -> RawMeeting | None:
    if not payload.get("id") or not payload.get("title"):
        return None
    listed = payload.get("attendees")
    return RawMeeting(
        source_id=str(payload["id"]),
        title=str(payload["title"]),
        held_on=_day(payload.get("start")),
        attendees=[
            str(p.get("name") or p.get("display_name") or "") if isinstance(p, dict) else str(p)
            for p in (listed if isinstance(listed, list) else [])
        ],
        summary=str(payload.get("summary") or ""),
        notes=str(payload.get("content") or ""),
        transcript=str(payload.get("transcript") or ""),
        link=payload.get("share_link"),
    )


def split_cut(transcript: str) -> tuple[str, int | None]:
    """Wispr ends a partial transcript with a marker. It is not something anyone said."""
    found = _CUT.search(transcript)
    if found is None:
        return transcript, None
    return transcript[: found.start()], int(found.group(1))


def classify_reply(sender: str, body: str) -> ReplyKind:
    """Only what a rule can be sure of. Whether a reply is interested is a person's call."""
    if _BOUNCE_SENDER.search(sender):
        return "bounced"
    return "opted_out" if _OPT_OUT.search(body) else "reply"


def _plain(text: str) -> str:
    return " ".join(text.split()).casefold()


def quote_found(quote: str, source: str) -> bool:
    wanted = _plain(quote)
    return bool(wanted) and wanted in _plain(source)


def lifecycle(
    record: dict[str, Any], replies: list[dict[str, Any]], meetings: list[dict[str, Any]]
) -> dict[str, Any]:
    """Each state needs its own proof. Sent is not delivered, and a reply is not a meeting."""
    reached = ["drafted"]
    status = record.get("status")
    if status == "rejected":
        return {"state": "rejected", "reached": [*reached, "rejected"]}
    reached.append("verified")
    if status == "approved":
        reached.append("approved")
    schedule = record.get("schedule") or {}
    if schedule.get("state") in ("scheduled", "due"):
        reached.append("scheduled")
    if not (record.get("test_sends") or record.get("manual_sends")):
        return {"state": reached[-1], "reached": reached}
    reached.append("sent")
    kinds = {r["kind"] for r in replies}
    if "bounced" in kinds:
        reached.append("bounced")
    elif kinds:
        reached.append("replied")
    if meetings:
        reached.append("booked")
    return {"state": reached[-1], "reached": reached}


def _wins(outcomes: Iterable[Outcome]) -> dict[str, list[str]]:
    wins: dict[str, list[str]] = defaultdict(list)
    for o in outcomes:
        if o.outreach_id and o.kind in WINS:
            wins[o.outreach_id].append(o.id)
    return wins


def _ready(t: Touch, wins: dict[str, list[str]], today: date) -> bool:
    return t.id in wins or t.sent_on <= today - timedelta(days=MATURITY_DAYS)


def _rate(touches: list[Touch], wins: dict[str, list[str]]) -> float:
    return sum(1 for t in touches if t.id in wins) / len(touches) if touches else 0.0


def _value(t: Touch, dimension: str) -> str | None:
    value = getattr(t, dimension)
    return None if value is None else str(value)


def _proposal(
    dimension: str, value: str, rows: list[Touch], others: list[Touch], wins: dict[str, list[str]]
) -> dict[str, Any]:
    rate, baseline = _rate(rows, wins), _rate(others, wins)
    return {
        "dimension": dimension,
        "value": value,
        "signal": value,
        "target": TARGETS[dimension],
        "sample": len(rows),
        "rate": round(rate, 3),
        "baseline": round(baseline, 3),
        "change": CHANGE_TEXT[dimension].format(value=value.replace("_", " ")),
        "caveat": "Correlation, not causation. These groups were not randomly assigned.",
        "checks": {
            "sample": len(rows),
            "selection_bias": True,
            "alternatives": "Timing, list quality or who was contacted could explain this.",
        },
        "outcome_ids": [i for t in rows for i in wins.get(t.id, [])],
    }


def compare(
    touches: list[Touch], outcomes: list[Outcome], today: date, modes: tuple[str, ...]
) -> dict[str, Any]:
    """Every dimension the records hold, against the sends that had a fair chance."""
    allowed = [t for t in touches if t.mode in modes]
    counted_outcomes = [o for o in outcomes if o.mode in modes]
    wins = _wins(counted_outcomes)
    ready = [t for t in allowed if _ready(t, wins, today)]
    known = {t.id for t in touches}
    gaps = [o for o in counted_outcomes if o.kind in WINS and o.outreach_id not in known]
    report: dict[str, Any] = {
        "counted": len(ready),
        "excluded": len(touches) - len(allowed),
        "pending": len(allowed) - len(ready),
        "attribution_gaps": len(gaps),
        "maturity_days": MATURITY_DAYS,
        "min_sample": MIN_SAMPLE,
        "groups": [],
        "proposals": [],
    }
    for dimension in TARGETS:
        grouped: dict[str, list[Touch]] = defaultdict(list)
        for t in ready:
            value = _value(t, dimension)
            if value is not None:
                grouped[value].append(t)
        for value, rows in grouped.items():
            report["groups"].append(
                {
                    "dimension": dimension,
                    "value": value,
                    "n": len(rows),
                    "wins": sum(1 for t in rows if t.id in wins),
                    "rate": round(_rate(rows, wins), 3),
                    "enough": len(rows) >= MIN_SAMPLE,
                }
            )
            others = [t for k, v in grouped.items() if k != value for t in v]
            if (
                len(rows) >= MIN_SAMPLE
                and len(others) >= MIN_SAMPLE
                and _rate(rows, wins) > _rate(others, wins)
            ):
                report["proposals"].append(_proposal(dimension, value, rows, others, wins))
    return report


def measure(after_rate: float, after_n: int, before_rate: float, before_n: int) -> dict[str, Any]:
    """Keep, roll back, or wait. Below the sample floor on either side, it says wait."""
    base = {
        "after_rate": round(after_rate, 3),
        "after_n": after_n,
        "before_rate": round(before_rate, 3),
        "before_n": before_n,
    }
    if min(after_n, before_n) < MIN_SAMPLE:
        return {**base, "verdict": "insufficient", "action": "wait"}
    gap = after_rate - before_rate
    if gap >= MIN_EFFECT:
        return {**base, "verdict": "improved", "action": "keep"}
    if gap <= -MIN_EFFECT:
        return {**base, "verdict": "worse", "action": "roll_back"}
    return {**base, "verdict": "no_change", "action": "keep_watching"}


def measure_experiment(
    version: int, touches: list[Touch], outcomes: list[Outcome], today: date, modes: tuple[str, ...]
) -> dict[str, Any]:
    """After the change against the holdout and everything before it."""
    wins = _wins(o for o in outcomes if o.mode in modes)
    ready = [t for t in touches if t.mode in modes and _ready(t, wins, today)]
    after = [
        t
        for t in ready
        if t.strategy_version is not None
        and t.strategy_version >= version
        and t.variant != "holdout"
    ]
    ids = {t.id for t in after}
    control = [t for t in ready if t.id not in ids]
    return measure(_rate(after, wins), len(after), _rate(control, wins), len(control))
