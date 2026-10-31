"""Conversation records per target, and the steps that move them. Autopilot's reply handling.

A conversation exists once someone replied to a message we sent. Its state is derived from what the
person wrote (checked by code) and what we have done. The Director only moves messages and calendar
events; it never decides what to say or when to meet."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from trigger_point.office.autopilot import Policy
from trigger_point.office.store import OfficeStore
from trigger_point.workflow.conversation import (
    OPEN_STATES,
    Analysis,
    Busy,
    analyse,
    confirm_text,
    new_token,
    offer_text,
    overlaps,
    suggest_slots,
)
from trigger_point.workflow.feedback import FeedbackService
from trigger_point.workflow.models import stable_id
from trigger_point.workflow.service import WorkflowService

Result = dict[str, Any]


class Conversations:
    def __init__(self, wf: WorkflowService, fb: FeedbackService, office: OfficeStore) -> None:
        self.wf, self.fb, self.office = wf, fb, office

    # ── records ─────────────────────────────────────────────────────────────────────────────

    def all(self, mission_id: str) -> list[dict[str, Any]]:
        return self.wf.engine.records("conversation", mission_id)

    def get(self, mission_id: str, target_id: str) -> dict[str, Any] | None:
        return next((c for c in self.all(mission_id) if c["target_id"] == target_id), None)

    def _save(self, mission_id: str, conv: dict[str, Any]) -> None:
        self.wf.engine.save_record("conversation", conv["id"], mission_id, conv)

    def _log(self, mission_id: str, conv: dict[str, Any], decision: str, text: str) -> None:
        self.office.log_autopilot(mission_id, "conversation", decision, text, conv["target_id"])

    def _open(self, mission_id: str, reply: dict[str, Any]) -> dict[str, Any]:
        found = self.get(mission_id, reply["target_id"])
        if found:
            return found
        outreach = self.wf._outreach_record(mission_id, reply["outreach_id"]) or {}  # noqa: SLF001
        sends = outreach.get("test_sends") or []
        return {
            "id": stable_id("cnv", mission_id, reply["target_id"]),
            "target_id": reply["target_id"],
            "target_name": reply["target_name"],
            "outreach_id": reply["outreach_id"],
            "subject": outreach.get("subject", ""),
            "thread_id": sends[0]["thread_id"] if sends else None,
            "state": "awaiting_reply",
            "turns": [
                {"who": "us", "text": outreach.get("body", ""), "at": self._now().isoformat()}
            ],
            "analysed": [],
            "slots": [],
            "outbox": None,
            "token": None,
            "token_used": False,
            "start": None,
            "decline_reason": None,
            "decline_quote": None,
            "note": "",
            "meeting_id": None,
        }

    def _now(self) -> datetime:
        return self.fb.now()

    def recipient(self, mission_id: str, target_id: str) -> str | None:
        """Demo goes to the demo inbox, live to the person. The Gmail guard checks it again."""
        if self.wf._settings.outreach_mode == "live":  # noqa: SLF001
            target = self.wf._target(mission_id, target_id) or {}  # noqa: SLF001
            return str(target.get("buyer_email") or "") or None
        return self.wf.test_recipients[0] if self.wf.test_recipients else None

    def _company(self, mission_id: str) -> str:
        m = self.wf.engine.mission(mission_id)
        ctx = self.wf._contexts.get(m.context_id) if m.context_id else None  # noqa: SLF001
        return (getattr(ctx, "company", None) or "The team") if ctx else "The team"

    def _domain(self, mission_id: str) -> str:
        m = self.wf.engine.mission(mission_id)
        ctx = self.wf._contexts.get(m.context_id) if m.context_id else None  # noqa: SLF001
        return ctx.domain if ctx else "unknown"

    # ── the founder's calendar ──────────────────────────────────────────────────────────────

    FRESH = timedelta(minutes=15)

    def record_busy(self, mission_id: str, items: list[dict[str, Any]]) -> Result:
        """Busy times the Director read from Google Calendar. Unreadable entries are dropped, and
        every time must carry an offset, so a vague 'afternoon' can never look like free time."""
        good: list[dict[str, str]] = []
        for item in items[:500]:
            try:
                a = datetime.fromisoformat(str(item["start"]))
                b = datetime.fromisoformat(str(item["end"]))
            except (KeyError, ValueError):
                continue
            if a.tzinfo is None or b.tzinfo is None or b <= a:
                continue
            good.append({"start": a.isoformat(), "end": b.isoformat()})
        rid = stable_id("cal", mission_id)
        record = {"id": rid, "fetched_at": self._now().isoformat(), "busy": good}
        self.wf.engine.save_record("calendar_busy", rid, mission_id, record)
        return {"ok": True, "busy": len(good), "skipped": len(items) - len(good)}

    def _calendar(self, mission_id: str) -> dict[str, Any] | None:
        rows = self.wf.engine.records("calendar_busy", mission_id)
        return rows[0] if rows else None

    def calendar_fresh(self, mission_id: str) -> bool:
        row = self._calendar(mission_id)
        if row is None:
            return False
        return self._now() - datetime.fromisoformat(row["fetched_at"]) < self.FRESH

    def busy(self, mission_id: str) -> Busy:
        row = self._calendar(mission_id) or {"busy": []}
        return [
            (datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"]))
            for b in row["busy"]
        ]

    def needs_calendar(self, mission_id: str) -> bool:
        """A reply is waiting that needs the calendar, and what we know is stale."""
        waiting = any(
            r["kind"] == "reply"
            and r["id"] not in (self.get(mission_id, r["target_id"]) or {}).get("analysed", [])
            for r in self.fb.replies(mission_id)
        )
        return waiting and not self.calendar_fresh(mission_id)

    # ── reading replies ─────────────────────────────────────────────────────────────────────

    def process(self, mission_id: str, policy: Policy) -> str | None:
        """Handles the oldest reply nobody has read yet, or closes a silent conversation."""
        now = self._now()
        fresh = self.calendar_fresh(mission_id)
        for reply in self.fb.replies(mission_id):
            conv = self._open(mission_id, reply)
            if reply["id"] in conv["analysed"]:
                continue
            if reply["kind"] == "reply" and not fresh:
                continue  # read it once the calendar has been checked: never offer a busy time
            conv["analysed"].append(reply["id"])
            conv["turns"].append({"who": "them", "text": reply["body"], "at": now.isoformat()})
            if conv["state"] not in OPEN_STATES and conv["state"] != "needs_you":
                self._save(mission_id, conv)
                continue
            self._apply(mission_id, policy, conv, reply, now)
            self._save(mission_id, conv)
            return f"reply:{reply['id']}"
        return self._silence(mission_id, policy, now)

    def _silence(self, mission_id: str, policy: Policy, now: datetime) -> str | None:
        for conv in self.all(mission_id):
            if conv["state"] != "awaiting_reply":
                continue
            last = datetime.fromisoformat(conv["turns"][-1]["at"])
            if now - last > timedelta(hours=policy.silence_hours):
                conv["state"], conv["note"] = (
                    "stalled",
                    f"No answer in {policy.silence_hours} hours",
                )
                self._save(mission_id, conv)
                self._log(mission_id, conv, "allow", f"{conv['target_name']}: no answer, closed")
                return f"stalled:{conv['target_id']}"
        return None

    def _apply(
        self,
        mission_id: str,
        policy: Policy,
        conv: dict[str, Any],
        reply: dict[str, Any],
        now: datetime,
    ) -> None:
        name = conv["target_name"]
        if reply["kind"] == "opted_out":
            self._decline(mission_id, conv, reply, "Asked not to be contacted again", "")
            return
        if reply["kind"] == "bounced":
            conv["state"], conv["note"] = "needs_you", "The email bounced"
            self._log(mission_id, conv, "hold", f"{name}: the email bounced")
            return
        if sum(1 for t in conv["turns"] if t["who"] == "us") > policy.max_turns:
            conv["state"], conv["note"] = "needs_you", "Reached the conversation limit"
            self._log(mission_id, conv, "hold", f"{name}: reached {policy.max_turns} turns")
            return
        a = policy.availability
        busy = self.busy(mission_id)
        out: Analysis = analyse(
            self.wf._llm,  # noqa: SLF001
            reply["body"],
            a.timezone,
            lambda t: a.allows(t) and not overlaps(t, a.minutes, busy),
            now,
            f"{self._domain(mission_id)}__reply",
        )
        if out.intent == "no":
            self._decline(mission_id, conv, reply, out.reason, out.quote)
        elif out.intent == "yes_with_time":
            conv.update(state="booking", start=out.start, token=new_token(), token_used=False)
            conv["note"] = ""
            self._log(mission_id, conv, "allow", f"{name} agreed to a time. Booking it")
        elif out.intent == "yes":
            slots = suggest_slots(a.days, a.start, a.end, a.timezone, a.minutes, now, busy=busy)
            if not slots:
                conv["state"], conv["note"] = "needs_you", "No free time inside your window"
                self._log(mission_id, conv, "hold", f"{name}: no time to offer")
                return
            body = offer_text(
                name_of(conv, self.wf, mission_id),
                self._company(mission_id),
                slots,
                a.timezone,
                a.minutes,
            )
            conv.update(state="replying", slots=slots, outbox=self._box("offer", conv, body))
            self._log(mission_id, conv, "allow", f"{name} is interested. Offering times")
        else:
            conv["state"] = "needs_you"
            conv["note"] = out.note or "Could not tell what they meant"
            self._log(mission_id, conv, "hold", f"{name}: {conv['note']}")

    def _box(self, kind: str, conv: dict[str, Any], body: str) -> dict[str, Any]:
        return {"kind": kind, "subject": f"Re: {conv['subject']}", "body": body, "sent": False}

    def _decline(
        self, mission_id: str, conv: dict[str, Any], reply: dict[str, Any], reason: str, quote: str
    ) -> None:
        conv.update(state="declined", decline_reason=reason, decline_quote=quote, outbox=None)
        self.fb.label_reply(mission_id, reply["id"], "negative")
        self.fb.suppress(mission_id, conv["target_id"], "declined")
        self._log(
            mission_id,
            conv,
            "allow",
            f"{conv['target_name']} said no: {reason or 'no reason given'}",
        )

    # ── tools the Director calls ────────────────────────────────────────────────────────────

    def prepare_reply(self, mission_id: str, target_id: str) -> Result:
        conv = self.get(mission_id, target_id)
        box = conv.get("outbox") if conv else None
        if not conv or not box or box["sent"]:
            return {"ok": False, "error": "nothing_to_send", "message": "no reply is waiting"}
        to = self.recipient(mission_id, target_id)
        if not to:
            return {"ok": False, "error": "no_recipient", "message": "no address to reply to"}
        return {
            "ok": True,
            "to": [to],
            "subject": box["subject"],
            "body": box["body"],
            "replyThreadId": conv["thread_id"],
        }

    def record_reply_sent(self, mission_id: str, target_id: str, message_id: str) -> Result:
        conv = self.get(mission_id, target_id)
        box = conv.get("outbox") if conv else None
        if not conv or not box or box["sent"]:
            return {"ok": False, "error": "nothing_to_send", "message": "no reply was waiting"}
        conv["outbox"] = {**box, "sent": True, "message_id": message_id}
        conv["turns"].append({"who": "us", "text": box["body"], "at": self._now().isoformat()})
        if box["kind"] == "offer":
            conv["state"] = "awaiting_reply"
        self._save(mission_id, conv)
        self._log(mission_id, conv, "allow", f"Replied to {conv['target_name']}")
        return {"ok": True}

    def get_booking(self, mission_id: str, target_id: str, minutes: int, zone: str) -> Result:
        conv = self.get(mission_id, target_id)
        if not conv or conv["state"] != "booking" or conv["token_used"] or not conv["start"]:
            return {"ok": False, "error": "no_booking", "message": "nothing to book"}
        to = self.recipient(mission_id, target_id)
        if not to:
            return {"ok": False, "error": "no_recipient", "message": "no address to invite"}
        start = datetime.fromisoformat(conv["start"])
        return {
            "ok": True,
            "title": f"{conv['token']} Intro call: {self._company(mission_id)} and {conv['target_name']}",
            "attendee": to,
            "start": conv["start"],
            "end": (start + timedelta(minutes=minutes)).isoformat(),
            "timezone": zone,
            "token": conv["token"],
            "meet": "Add a Google Meet link and invite the attendee.",
        }

    def booking_for(self, mission_id: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:
        """The booking this calendar call belongs to: its code must appear in the event."""
        blob = str(tool_input)
        for conv in self.all(mission_id):
            if conv["state"] == "booking" and conv["token"] and conv["token"] in blob:
                return conv
        return None

    def record_booked_meeting(
        self,
        mission_id: str,
        target_id: str,
        token: str,
        event_id: str,
        link: str,
        minutes: int,
        zone: str,
    ) -> Result:
        conv = self.get(mission_id, target_id)
        if not conv or conv["state"] != "booking" or conv["token_used"] or conv["token"] != token:
            return {"ok": False, "error": "no_booking", "message": "that booking is not open"}
        start = datetime.fromisoformat(conv["start"]).astimezone(ZoneInfo(zone))
        target = self.wf._target(mission_id, target_id) or {}  # noqa: SLF001
        live = self.wf._settings.outreach_mode == "live"  # noqa: SLF001
        rid = stable_id("mtg", mission_id, token)
        record = {
            "id": rid,
            "mission_id": mission_id,
            "title": f"Intro call with {conv['target_name']}",
            "held_on": start.date().isoformat(),
            "time": f"{start:%H:%M}",
            "account_name": conv["target_name"],
            "attendee": target.get("buyer_name") or conv["target_name"],
            "attendee_role": target.get("buyer_title") or "",
            "audience": target.get("audience", ""),
            "link": link or None,
            "event_id": event_id,
            "source": "autopilot",
            "prep": self._prep(mission_id, conv, target),
            "demo": not live,
        }
        self.wf.engine.save_record("meeting", rid, mission_id, record)
        self.wf.record_outcome(
            mission_id,
            {
                "kind": "meeting_booked",
                "occurred_on": record["held_on"],
                "account_name": conv["target_name"],
                "source": "autopilot",
                "note": f"Booked by Autopilot: {record['title']}",
            },
            mode=None if live else "test",
        )
        conv.update(state="booked", token_used=True, meeting_id=rid)
        body = confirm_text(
            target.get("buyer_name") or conv["target_name"],
            self._company(mission_id),
            conv["start"],
            zone,
            link,
        )
        conv["outbox"] = self._box("confirm", conv, body)
        self._save(mission_id, conv)
        self._log(
            mission_id, conv, "allow", f"Booked {conv['target_name']} for {start:%a %d %b %H:%M}"
        )
        return {"ok": True, "meeting_id": rid}

    def _prep(self, mission_id: str, conv: dict[str, Any], target: dict[str, Any]) -> str:
        who = target.get("buyer_name")
        title = target.get("buyer_title")
        parts = [
            f"You are meeting {who}{f', {title}' if title else ''} at {conv['target_name']}."
            if who
            else f"You are meeting {conv['target_name']}."
        ]
        for why in (target.get("why_now") or [])[:2]:
            parts.append(f"Why now: {why.rstrip('.')}.")
        said = next((t["text"] for t in reversed(conv["turns"]) if t["who"] == "them"), "")
        if said:
            first = " ".join(said.split())[:160]
            parts.append(f'Their reply: "{first}".')
        parts.append("Open question: what would a pilot need to look like for them?")
        return " ".join(parts)


def name_of(conv: dict[str, Any], wf: WorkflowService, mission_id: str) -> str:
    target = wf._target(mission_id, conv["target_id"]) or {}  # noqa: SLF001
    return str(target.get("buyer_name") or conv["target_name"])
