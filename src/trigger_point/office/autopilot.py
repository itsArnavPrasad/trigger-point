"""Autopilot: standing, scoped, audited approvals for the steps a founder should not have to click.

`decide` is pure. It answers allow or hold and never deny: anything it is unsure about is held, so
it lands in "Needs you" exactly as it did before Autopilot existed. The send guard hook stays the
floor underneath this; Autopilot can only answer the Claude Code permission prompt."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator

from trigger_point.office.store import OfficeStore

GLOBAL = "*"
GMAIL_SEND = "mcp__claude_ai_Gmail__send_message"
GMAIL_READ = "mcp__claude_ai_Gmail__get_thread"
CALENDAR_CREATE = "mcp__claude_ai_Google_Calendar__create_event"
CREDIT_TOOLS = {"discover_accounts", "research_account_signals", "map_buying_committee"}
GATE_TOOLS = {"approve_business_profile", "approve_icp_plan", "approve_campaign_draft"}
# Learning decisions (lessons, plans, experiments, proposals, rollbacks) and Wispr are not here:
# they stay human (CLAUDE.md rule 15).
AUTO_TOOLS = (
    GATE_TOOLS
    | CREDIT_TOOLS
    | {"list_open_threads", "sync_replies", "prepare_reply", "record_reply_sent"}
    | {"get_booking", "record_booked_meeting", "record_busy_times"}
    | {GMAIL_SEND, GMAIL_READ, CALENDAR_CREATE}
)
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
EMAIL = re.compile(r"[^\s@<>,;]+@[^\s@<>,;]+\.[^\s@<>,;]+")


class Availability(BaseModel):
    days: list[int] = Field(default=[0, 1, 2, 3, 4], min_length=1)  # Monday is 0
    start: str = "10:00"
    end: str = "17:00"
    timezone: str = "Asia/Kolkata"
    minutes: int = Field(default=30, ge=15, le=180)

    @field_validator("start", "end")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        if not HHMM.match(v):
            raise ValueError("time must be HH:MM")
        return v

    @field_validator("days")
    @classmethod
    def _days(cls, v: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("days are 0 (Monday) to 6 (Sunday)")
        return sorted(set(v))

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("unknown timezone") from exc
        return v

    @model_validator(mode="after")
    def _order(self) -> Availability:
        if self.start >= self.end:
            raise ValueError("start must be before end")
        return self

    def allows(self, start: datetime) -> bool:
        """True when a meeting of `minutes` beginning at `start` fits inside the window."""
        if start.tzinfo is None:
            return False
        local = start.astimezone(ZoneInfo(self.timezone))
        if local.weekday() not in self.days:
            return False
        opens = datetime.combine(local.date(), time.fromisoformat(self.start), local.tzinfo)
        closes = datetime.combine(local.date(), time.fromisoformat(self.end), local.tzinfo)
        return opens <= local and local + timedelta(minutes=self.minutes) <= closes


class Policy(BaseModel):
    enabled: bool = True
    paused: bool = False
    credit_cap: int = Field(default=50, ge=0, le=100000)
    meetings_wanted: int = Field(default=5, ge=1, le=100)
    daily_send_cap: int = Field(default=20, ge=1, le=500)
    auto_approve_outreach: bool = True
    availability: Availability = Field(default_factory=Availability)
    send_window: Availability = Field(
        default_factory=lambda: Availability(start="09:30", end="17:30", minutes=15)
    )
    max_turns: int = Field(default=6, ge=1, le=20)
    silence_hours: int = Field(default=72, ge=1, le=720)

    @property
    def active(self) -> bool:
        return self.enabled and not self.paused


@dataclass(frozen=True)
class Context:
    """Everything `decide` may look at, gathered by the caller so `decide` does no I/O."""

    known_mission: bool
    session_mission: str | None
    credits_spent: Decimal
    projected_credits: Decimal
    allowed_recipients: frozenset[str]
    sends_today: int
    meetings_booked: int
    booking_attendees: frozenset[str] = frozenset()  # attendees of an unused booking token
    token_in_use: bool = False


@dataclass(frozen=True)
class Decision:
    verdict: Literal["allow", "hold"]
    reason: str

    @property
    def allowed(self) -> bool:
        return self.verdict == "allow"


def _calendar_read(tool: str) -> bool:
    """Looking at the founder's calendar changes nothing, so reading it needs no click."""
    prefix = "mcp__claude_ai_Google_Calendar__"
    return tool.startswith(prefix) and tool.removeprefix(prefix).startswith(
        ("list_", "get_", "suggest_", "find_", "search_")
    )


def _hold(reason: str) -> Decision:
    return Decision("hold", reason)


def _addresses(value: Any) -> set[str] | None:
    """Every address found in a to/attendees value, or None when the shape is not understood."""
    if value is None or value == "":
        return set()
    if isinstance(value, str):
        return {m.casefold() for m in EMAIL.findall(value)}
    if isinstance(value, list):
        out: set[str] = set()
        for v in value:
            if isinstance(v, dict):
                v = v.get("email") or v.get("address") or ""
            got = _addresses(v)
            if got is None:
                return None
            out |= got
        return out
    return None


def decide(policy: Policy, ctx: Context, tool: str, tool_input: Mapping[str, Any]) -> Decision:
    tool = tool.removeprefix("mcp__trigger_point__")
    if not policy.enabled:
        return _hold("Autopilot is off")
    if policy.paused:
        return _hold("Autopilot is paused")
    if not ctx.known_mission:
        return _hold("The mission is not known to Autopilot")
    claimed = tool_input.get("mission_id")
    if claimed is not None and claimed != ctx.session_mission:
        return _hold("The tool names a different mission than this session")
    if tool not in AUTO_TOOLS and not _calendar_read(tool):
        return _hold("This decision is yours to make")
    if tool in CREDIT_TOOLS and ctx.credits_spent + ctx.projected_credits > policy.credit_cap:
        return _hold(
            f"Would pass the {policy.credit_cap} credit cap "
            f"({ctx.credits_spent} spent, up to {ctx.projected_credits} more)"
        )
    if tool == GMAIL_SEND:
        return _gmail(policy, ctx, tool_input)
    if tool == CALENDAR_CREATE:
        return _calendar(policy, ctx, tool_input)
    return Decision("allow", "Within the Autopilot policy")


def _gmail(policy: Policy, ctx: Context, tool_input: Mapping[str, Any]) -> Decision:
    if tool_input.get("draftId"):
        return _hold("Sending a saved draft is not covered")
    to: set[str] = set()
    for key in ("to", "cc", "bcc"):
        got = _addresses(tool_input.get(key))
        if got is None:
            return _hold("Could not read the recipients")
        to |= got
    if not to:
        return _hold("No recipient")
    if not to <= ctx.allowed_recipients:
        return _hold("A recipient is not on the allowed list")
    if ctx.sends_today >= policy.daily_send_cap:
        return _hold(f"Reached today's cap of {policy.daily_send_cap} messages")
    return Decision("allow", "Sent to an allowed recipient within the daily cap")


def _calendar(policy: Policy, ctx: Context, tool_input: Mapping[str, Any]) -> Decision:
    if ctx.meetings_booked >= policy.meetings_wanted:
        return _hold(f"Already booked the {policy.meetings_wanted} meetings you wanted")
    if not ctx.booking_attendees or ctx.token_in_use:
        return _hold("No confirmed time to book")
    for key in ("attendees", "guests", "attendeeEmails"):
        got = _addresses(tool_input.get(key))
        if got:
            if got <= ctx.booking_attendees and got <= ctx.allowed_recipients:
                return Decision("allow", "Booking a time the person confirmed")
            return _hold("An attendee does not match the confirmed booking")
    return _hold("The event has no attendee")


def credits_total(credits: Mapping[str, str] | None) -> Decimal:
    """Spent plus unconfirmed estimate. An unreadable number counts as unknown, never zero."""
    total = Decimal(0)
    for key in ("actual", "unconfirmed_estimate"):
        raw = (credits or {}).get(key)
        if raw in (None, ""):
            continue
        try:
            total += Decimal(str(raw))
        except InvalidOperation:
            return Decimal("1e9")
    return total


class AutopilotService:
    """Policy storage and the audit log. Per-mission row, then the global row, then the default."""

    def __init__(self, office: OfficeStore, default_on: bool = True) -> None:
        self.office = office
        self.default_on = default_on

    def policy_for(self, mission_id: str) -> Policy:
        for key in (mission_id, GLOBAL):
            body = self.office.autopilot_body(key)
            if body is not None:
                return Policy.model_validate(body)
        return Policy(enabled=self.default_on)

    def save(self, mission_id: str, changes: Mapping[str, Any]) -> Policy:
        base = self.policy_for(mission_id).model_dump()
        merged = {**base, **changes}
        policy = Policy.model_validate(merged)  # raises on bad input; nothing is stored then
        self.office.set_autopilot_body(mission_id, policy.model_dump())
        return policy
