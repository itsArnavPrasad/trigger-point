"""Replies, schedules, meetings and the learning loop, over the records WorkflowService keeps.

The spec's nine steps: capture a verified event, link it, extract a candidate lesson, check it,
propose a change, get approval, version it, measure it, then keep or roll back. Only the Office
can approve: no MCP tool here decides a lesson, a proposal or an experiment."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ValidationError

from trigger_point.workflow.gtm import MIN_SAMPLE
from trigger_point.workflow.loop import (
    MAX_SOURCE_CHARS,
    InsightKind,
    RawMeeting,
    Touch,
    classify_reply,
    compare,
    lifecycle,
    measure_experiment,
    parse_gmail_messages,
    parse_meeting,
    quote_found,
    split_cut,
    unwrap_tool_response,
)
from trigger_point.workflow.models import stable_id
from trigger_point.workflow.service import (
    Result,
    WorkflowService,
    guarded,
    outcome_mode,
    teach_modes,
)

GMAIL_READ = ("mcp__claude_ai_Gmail__get_thread", "mcp__claude_ai_Gmail__get_message")
WISPR_READ = (
    "mcp__claude_ai_Wispr_Flow__get_meeting",
    "mcp__claude_ai_Wispr_Flow__get_meeting_by_calendar_id",
)
CAPTURED = (*GMAIL_READ, *WISPR_READ)
MAX_STEPS = 3  # a sequence never goes past this many messages to one target
MISSED_AFTER = timedelta(hours=2)
USABLE = ("verified", "confirmed")
STOP_KINDS = ("reply", "opted_out", "bounced")
DEMO_TOUCHES = (("school_authority", 3), ("parent", 0))
DEMO_SIGNALS = {"school_authority": ["topic_engagement"], "parent": ["active_hiring"]}


class InsightIn(BaseModel):
    kind: InsightKind
    text: str
    basis: Literal["statement", "interpretation"]
    quote: str = ""
    speaker: str | None = None
    ambiguous: bool = False


class FeedbackService:
    def __init__(self, wf: WorkflowService) -> None:
        self.wf, self.engine = wf, wf.engine
        self.now: Callable[[], datetime] = lambda: datetime.now(UTC)

    # ── raw capture ─────────────────────────────────────────────────────────────────────────

    def capture(
        self, mission_id: str, tool: str, tool_input: dict[str, Any], response: Any
    ) -> Result:
        """Keeps what the provider returned, so nothing later depends on a model's typing."""
        if tool not in CAPTURED:
            return {"ok": False, "error": "not_captured", "message": tool}
        payload = unwrap_tool_response(response)
        if payload is None:
            return {"ok": False, "error": "unreadable", "message": "no JSON in the response"}
        key = payload.get("id") or tool_input.get("threadId") or tool_input.get("messageId")
        if not key:
            return {"ok": False, "error": "unreadable", "message": "no id in the response"}
        part = (tool_input.get("view_transcript") or {}).get("start_char", 0)
        rid = stable_id("raw", mission_id, tool, key, part)
        body = {
            "id": rid,
            "tool": tool,
            "key": str(key),
            "part": part,
            "calendar_id": tool_input.get("calendar_id"),
            "payload": payload,
        }
        self.engine.save_record("raw_source", rid, mission_id, body)
        return {"ok": True, "id": rid}

    def _raw(self, mission_id: str, tools: tuple[str, ...]) -> list[dict[str, Any]]:
        return [r for r in self.engine.records("raw_source", mission_id) if r["tool"] in tools]

    # ── replies ─────────────────────────────────────────────────────────────────────────────

    def replies(self, mission_id: str) -> list[dict[str, Any]]:
        return self.engine.records("reply", mission_id)

    def open_threads(self, mission_id: str) -> Result:
        """Gmail threads worth reading. Read each with get_thread, then call sync_replies."""
        threads = [
            {"outreach_id": o["id"], "thread_id": s["thread_id"]}
            for o in self.wf.outreach(mission_id)
            for s in o.get("test_sends", [])
        ]
        return {"ok": True, "threads": threads}

    @guarded
    def sync_replies(self, mission_id: str) -> Result:
        """Turns captured threads into replies. Sender and text come from Gmail, not a model."""
        self.engine.mission(mission_id)
        sends = {
            s["thread_id"]: o for o in self.wf.outreach(mission_id) for s in o.get("test_sends", [])
        }
        seen = {r["id"] for r in self.replies(mission_id)}
        added = 0
        for raw in self._raw(mission_id, GMAIL_READ):
            for m in parse_gmail_messages(raw["payload"]):
                outreach = sends.get(m.thread_id or raw["key"])
                if outreach is None or m.ours or m.id in seen:
                    continue
                self._add_reply(mission_id, outreach, m.id, m.sender, m.body, m.received_on)
                seen.add(m.id)
                added += 1
        return {"ok": True, "added": added, "replies": len(seen)}

    def _add_reply(
        self,
        mission_id: str,
        outreach: dict[str, Any],
        message_id: str,
        sender: str,
        body: str,
        received_on: date | None,
    ) -> None:
        kind = classify_reply(sender, body)
        record = {
            "id": message_id,
            "outreach_id": outreach["id"],
            "target_id": outreach["target_id"],
            "target_name": outreach["target_name"],
            "sender": sender,
            "body": body[:2000],
            "received_on": (received_on or self.wf.today()).isoformat(),
            "kind": kind,
            "label": None,
        }
        self.engine.save_record("reply", message_id, mission_id, record)
        self._outcome(mission_id, outreach, kind, record["received_on"])
        if kind != "reply":
            self._suppress(mission_id, outreach["target_id"], outreach["target_name"], kind)

    def _outcome(self, mission_id: str, outreach: dict[str, Any], kind: str, on: str) -> Result:
        """A test send stays a test, whatever came back from it."""
        tested = bool(outreach.get("test_sends")) and not outreach.get("manual_sends")
        return self.wf.record_outcome(
            mission_id,
            {
                "kind": kind,
                "occurred_on": on,
                "account_name": outreach["target_name"],
                "outreach_id": outreach["id"],
                "audience": outreach["audience"],
                "strategy_version": outreach.get("strategy_version"),
                "source": "gmail",
            },
            mode="test" if tested else None,
        )

    @guarded
    def label_reply(self, mission_id: str, reply_id: str, label: str) -> Result:
        """Whether someone is interested is a person's reading, so it is a person's click."""
        reply = next((r for r in self.replies(mission_id) if r["id"] == reply_id), None)
        if reply is None:
            return {"ok": False, "error": "not_found", "message": reply_id}
        self.engine.save_record("reply", reply_id, mission_id, {**reply, "label": label})
        outreach = self.wf._outreach_record(mission_id, reply["outreach_id"])  # noqa: SLF001
        assert outreach is not None  # noqa: S101 - a reply exists only for a known message
        kind = {"positive": "positive_reply", "negative": "closed_lost", "opted_out": "opted_out"}
        self._outcome(mission_id, outreach, kind[label], self.wf.today().isoformat())
        if label == "opted_out":
            self._suppress(mission_id, reply["target_id"], reply["target_name"], "opted_out")
        return {"ok": True, "label": label}

    # ── suppression, schedules, sequences ───────────────────────────────────────────────────

    def suppressions(self, mission_id: str) -> list[dict[str, Any]]:
        return self.engine.records("suppression", mission_id)

    def _suppress(self, mission_id: str, target_id: str, name: str, reason: str) -> None:
        rid = stable_id("sup", mission_id, target_id)
        record = {"id": rid, "target_id": target_id, "target_name": name, "reason": reason}
        self.engine.save_record("suppression", rid, mission_id, record)
        for o in self.wf.outreach(mission_id):
            if o["target_id"] == target_id and o.get("schedule", {}).get("state") == "scheduled":
                self._set_schedule(mission_id, o, "cancelled", f"Stopped: {reason}")

    @guarded
    def suppress(self, mission_id: str, target_id: str, reason: str) -> Result:
        target = next((t for t in self.wf.targets(mission_id) if t["id"] == target_id), None)
        if target is None:
            return {"ok": False, "error": "not_found", "message": target_id}
        self._suppress(mission_id, target_id, target["name"], reason)
        return {"ok": True}

    def _set_schedule(
        self, mission_id: str, record: dict[str, Any], state: str, error: str | None = None
    ) -> None:
        schedule = {**record["schedule"], "state": state, "error": error}
        self.engine.save_record(
            "outreach", record["id"], mission_id, {**record, "schedule": schedule}
        )

    def _duplicate(self, mission_id: str, record: dict[str, Any]) -> bool:
        return any(
            o["target_id"] == record["target_id"]
            and o["content_hash"] == record["content_hash"]
            and (o.get("test_sends") or o.get("manual_sends"))
            for o in self.wf.outreach(mission_id)
        )

    @guarded
    def schedule_send(self, mission_id: str, outreach_id: str, send_at: str, tz: str) -> Result:
        record = self.wf._outreach_record(mission_id, outreach_id)  # noqa: SLF001
        if record is None:
            return {"ok": False, "error": "not_found", "message": outreach_id}
        try:
            when = datetime.fromisoformat(send_at).replace(tzinfo=ZoneInfo(tz))
        except (ValueError, ZoneInfoNotFoundError):
            return {"ok": False, "error": "bad_time", "message": "give a valid time and timezone"}
        if when <= self.now():
            return {"ok": False, "error": "bad_time", "message": "that time has passed"}
        if self.wf.is_suppressed(mission_id, record["target_id"]):
            return {"ok": False, "error": "suppressed", "message": "this target opted out"}
        if self._duplicate(mission_id, record):
            return {"ok": False, "error": "duplicate", "message": "this exact text already went"}
        record = self.wf._recheck(mission_id, record)  # noqa: SLF001
        if record["status"] not in ("verified", "approved"):
            return {"ok": False, "error": "not_verified", "message": "fix the findings first"}
        schedule = {
            "send_at": when.isoformat(),
            "timezone": tz,
            "state": "scheduled",
            "channel": "email",
            "recipient": "test inbox",
            "step": record.get("step", 1),
            "error": None,
        }
        self.engine.save_record(
            "outreach", outreach_id, mission_id, {**record, "schedule": schedule}
        )
        return {"ok": True, "schedule": schedule}

    @guarded
    def cancel_schedule(self, mission_id: str, outreach_id: str) -> Result:
        record = self.wf._outreach_record(mission_id, outreach_id)  # noqa: SLF001
        if record is None or not record.get("schedule"):
            return {"ok": False, "error": "not_found", "message": outreach_id}
        self._set_schedule(mission_id, record, "cancelled")
        return {"ok": True}

    def due_sends(self, mission_id: str) -> list[str]:
        """Marks what has come due. A send held too long is reported missed, never sent late."""
        due = []
        for o in self.wf.outreach(mission_id):
            schedule = o.get("schedule") or {}
            state = schedule.get("state")
            if state not in ("scheduled", "due"):
                continue
            when = datetime.fromisoformat(schedule["send_at"])
            if self.now() - when > MISSED_AFTER:
                self._set_schedule(mission_id, o, "missed", "Not sent in time")
            elif state == "scheduled" and when <= self.now():
                self._set_schedule(mission_id, o, "due")
                due.append(o["id"])
        return due

    @guarded
    def write_follow_up(self, mission_id: str, outreach_id: str) -> Result:
        """The next step of a sequence. Any answer, or the sequence's end, stops it."""
        parent = self.wf._outreach_record(mission_id, outreach_id)  # noqa: SLF001
        if parent is None:
            return {"ok": False, "error": "not_found", "message": outreach_id}
        if not (parent.get("test_sends") or parent.get("manual_sends")):
            return {"ok": False, "error": "not_sent", "message": "send the first message first"}
        if parent.get("step", 1) >= MAX_STEPS:
            return {"ok": False, "error": "sequence_ended", "message": f"{MAX_STEPS} is the limit"}
        answered = any(
            r["target_id"] == parent["target_id"] and r["kind"] in STOP_KINDS
            for r in self.replies(mission_id)
        )
        if answered or self.wf.is_suppressed(mission_id, parent["target_id"]):
            return {"ok": False, "error": "stopped", "message": "they answered, so this stops"}
        return self.wf.write_outreach(mission_id, parent["target_id"], follow_up_of=outreach_id)

    @guarded
    def mark_sent(self, mission_id: str, outreach_id: str, sent_on: str) -> Result:
        """A person sent this themselves. This is the real send that can teach."""
        record = self.wf._outreach_record(mission_id, outreach_id)  # noqa: SLF001
        if record is None:
            return {"ok": False, "error": "not_found", "message": outreach_id}
        if record["status"] != "approved":
            return {"ok": False, "error": "not_approved", "message": "approve this text first"}
        sends = [*record.get("manual_sends", []), {"sent_on": sent_on}]
        self.engine.save_record(
            "outreach", outreach_id, mission_id, {**record, "manual_sends": sends}
        )
        return {"ok": True}

    def touches(self, mission_id: str) -> list[Touch]:
        mission = self.engine.mission(mission_id)
        found = [Touch.model_validate(t) for t in self.engine.records("touch", mission_id)]
        for o in self.wf.outreach(mission_id):
            sent = o.get("manual_sends") or o.get("test_sends")
            if not sent:
                continue
            real = bool(o.get("manual_sends"))
            mode = (
                outcome_mode(mission.mode, {"account_name": o["target_name"]}) if real else "test"
            )
            found.append(
                Touch(
                    id=o["id"],
                    account_name=o["target_name"],
                    audience=o["audience"],
                    variant=o.get("variant", "none"),
                    signal_types=o.get("signal_types", []),
                    strategy_version=o.get("strategy_version"),
                    sent_on=sent[0].get("sent_on") or self.wf.today(),
                    mode=mode,
                )
            )
        return found

    # ── meetings ────────────────────────────────────────────────────────────────────────────

    def _continue_from(self, mission_id: str, source_id: str) -> int | None:
        """Where the transcript was cut, if the rest has not been read."""
        parts = self._parts(mission_id, source_id)
        if not parts:
            return None
        return split_cut(str(parts[-1]["payload"].get("transcript") or ""))[1]

    def _parts(self, mission_id: str, source_id: str) -> list[dict[str, Any]]:
        rows = (r for r in self._raw(mission_id, WISPR_READ) if r["key"] == source_id)
        return sorted(rows, key=lambda r: r["part"])

    def _meeting_source(self, mission_id: str, source_id: str) -> RawMeeting | None:
        parts = self._parts(mission_id, source_id)
        if not parts:
            return None
        meeting = parse_meeting(parts[0]["payload"])
        if meeting is None:
            return None
        text = "\n".join(split_cut(str(p["payload"].get("transcript") or ""))[0] for p in parts)
        return meeting.model_copy(update={"transcript": text[:MAX_SOURCE_CHARS]})

    def _match(
        self, mission_id: str, raw: RawMeeting, source_id: str, suggested: str | None
    ) -> tuple[str | None, str]:
        """A verified identifier, or a name in the record. A suggestion alone needs a person."""
        calendars = {
            r["calendar_id"]
            for r in self._raw(mission_id, WISPR_READ)
            if r["key"] == source_id and r.get("calendar_id")
        }
        for meeting in self.wf.meetings(mission_id):
            if meeting.get("event_id") in calendars:
                return meeting.get("account_name"), "calendar"
        haystack = " ".join([raw.title, *raw.attendees]).casefold()
        for target in self.wf.targets(mission_id):
            if target["name"].casefold() in haystack:
                return target["name"], "name"
        return (suggested, "suggested") if suggested else (None, "none")

    @guarded
    def import_meeting(
        self, mission_id: str, source_id: str, suggested_account: str | None = None
    ) -> Result:
        """From the captured Wispr record. It must have been read first, so nothing is typed in."""
        self.engine.mission(mission_id)
        raw = self._meeting_source(mission_id, source_id)
        if raw is None:
            return {"ok": False, "error": "not_read", "message": "read it with get_meeting first"}
        cut = self._continue_from(mission_id, source_id)
        if cut is not None:
            message = "read the rest with view_transcript.start_char"
            return {"ok": False, "error": "incomplete", "message": message, "continue_from": cut}
        rid = stable_id("mtg", mission_id, source_id)
        if any(m["id"] == rid for m in self.wf.meetings(mission_id)):
            return {"ok": True, "id": rid, "already_imported": True}
        account, basis = self._match(mission_id, raw, source_id, suggested_account)
        linked = basis in ("calendar", "name")
        versions = self.engine.icp_versions(mission_id)
        record = {
            "id": rid,
            "mission_id": mission_id,
            "source": "wispr",
            "source_id": source_id,
            "title": raw.title,
            "held_on": (raw.held_on or self.wf.today()).isoformat(),
            "account_name": account,
            "match_basis": basis,
            "needs_review": not linked,
            "attendees": raw.attendees,
            "summary": raw.summary[:4000],
            "link": raw.link,
            "has_transcript": bool(raw.transcript),
            "strategy_version": self.wf.strategy_version(mission_id),
            "icp_version": versions[-1].version if versions else None,
            "progress": None,
        }
        self.engine.save_record("meeting", rid, mission_id, record)
        if linked:
            self._held(mission_id, record)
        return {"ok": True, "id": rid, "account_name": account, "match_basis": basis}

    def _held(self, mission_id: str, meeting: dict[str, Any]) -> None:
        self.wf.record_outcome(
            mission_id,
            {
                "kind": "meeting_held",
                "occurred_on": meeting["held_on"],
                "account_name": meeting["account_name"],
                "source": "wispr",
                "note": f"Meeting: {meeting['title']}",
            },
        )

    def _meeting(self, mission_id: str, meeting_id: str) -> dict[str, Any] | None:
        return next((m for m in self.wf.meetings(mission_id) if m["id"] == meeting_id), None)

    @guarded
    def link_meeting(self, mission_id: str, meeting_id: str, account_name: str) -> Result:
        """A person's answer to the review queue."""
        meeting = self._meeting(mission_id, meeting_id)
        if meeting is None:
            return {"ok": False, "error": "not_found", "message": meeting_id}
        updated = {
            **meeting,
            "account_name": account_name,
            "match_basis": "person",
            "needs_review": False,
        }
        self.engine.save_record("meeting", meeting_id, mission_id, updated)
        self._held(mission_id, updated)
        return {"ok": True}

    @guarded
    def set_progress(self, mission_id: str, meeting_id: str, progress: str) -> Result:
        meeting = self._meeting(mission_id, meeting_id)
        if meeting is None:
            return {"ok": False, "error": "not_found", "message": meeting_id}
        self.engine.save_record(
            "meeting", meeting_id, mission_id, {**meeting, "progress": progress}
        )
        if progress == "disqualified":
            self.wf.record_outcome(
                mission_id,
                {
                    "kind": "disqualified",
                    "occurred_on": self.wf.today().isoformat(),
                    "account_name": meeting.get("account_name"),
                    "source": meeting["source"],
                },
            )
        return {"ok": True}

    def insights(self, mission_id: str) -> list[dict[str, Any]]:
        """Reviewed insights from imported meetings, plus what a person typed after a meeting.
        A stored record (a person's review) wins over the same insight derived from a meeting."""
        stored = self.engine.records("insight", mission_id)
        derived = self._typed_learnings(mission_id)
        return list({i["id"]: i for i in [*derived, *stored]}.values())

    def _typed_learnings(self, mission_id: str) -> list[dict[str, Any]]:
        """A founder's own conclusion from a meeting is already a person's reading, so it counts
        as confirmed. A meeting that was missed or cancelled taught nothing."""
        found = []
        for m in self.wf.meetings(mission_id):
            if m.get("status") in ("missed", "cancelled"):
                continue
            for text in (str(t).strip() for t in m.get("learnings") or []):
                if not text:
                    continue
                found.append(
                    {
                        "id": stable_id("ins", mission_id, m["id"], "learning", text),
                        "kind": "learning",
                        "text": text,
                        "basis": "user_stated",
                        "quote": "",
                        "speaker": None,
                        "ambiguous": False,
                        "meeting_id": m["id"],
                        "account_name": m.get("account_name"),
                        "strategy_version": m.get("strategy_version"),
                        "status": "confirmed",
                        "original_text": None,
                        "source_link": m.get("link"),
                    }
                )
        return found

    @guarded
    def add_insights(
        self, mission_id: str, meeting_id: str, insights: list[dict[str, Any]]
    ) -> Result:
        """A statement stands only if its quote is in the source. The rest goes to review."""
        meeting = self._meeting(mission_id, meeting_id)
        if meeting is None or meeting["source"] != "wispr":
            return {"ok": False, "error": "not_found", "message": meeting_id}
        raw = self._meeting_source(mission_id, meeting["source_id"])
        source = raw.text if raw else ""
        saved, refused = 0, []
        for item in insights:
            try:
                i = InsightIn.model_validate(item)
            except ValidationError:
                refused.append({"text": str(item.get("text")), "reason": "invalid"})
                continue
            if i.basis == "statement" and not quote_found(i.quote, source):
                refused.append({"text": i.text, "reason": "quote_not_in_source"})
                continue
            rid = stable_id("ins", mission_id, meeting_id, i.kind, i.text)
            status = "verified" if i.basis == "statement" and not i.ambiguous else "needs_review"
            record = {
                **i.model_dump(),
                "id": rid,
                "meeting_id": meeting_id,
                "account_name": meeting.get("account_name"),
                "strategy_version": meeting.get("strategy_version"),
                "status": status,
                "original_text": None,
                "source_link": meeting.get("link"),
            }
            self.engine.save_record("insight", rid, mission_id, record)
            saved += 1
        return {"ok": True, "saved": saved, "refused": refused}

    @guarded
    def review_insight(
        self, mission_id: str, insight_id: str, action: str, text: str | None = None
    ) -> Result:
        """A correction keeps the original beside it."""
        insight = next((i for i in self.insights(mission_id) if i["id"] == insight_id), None)
        if insight is None:
            return {"ok": False, "error": "not_found", "message": insight_id}
        updated = {**insight, "status": {"reject": "rejected"}.get(action, "confirmed")}
        if action == "correct" and text:
            updated |= {"text": text, "original_text": insight["text"]}
        self.engine.save_record("insight", insight_id, mission_id, updated)
        return {"ok": True, "status": updated["status"]}

    # ── lessons ─────────────────────────────────────────────────────────────────────────────

    def lessons(self, mission_id: str) -> list[dict[str, Any]]:
        return self.engine.records("lesson", mission_id)

    def _lesson(self, mission_id: str, lesson_id: str) -> dict[str, Any] | None:
        return next((x for x in self.lessons(mission_id) if x["id"] == lesson_id), None)

    def _domain(self, mission_id: str) -> str:
        m = self.engine.mission(mission_id)
        ctx = self.wf._contexts.get(m.context_id) if m.context_id else None  # noqa: SLF001
        return ctx.domain if ctx else ""

    def learning_inputs(self, mission_id: str) -> Result:
        """Usable insights and teachable outcomes, for finding what repeats."""
        modes = teach_modes(self.engine.mission(mission_id).mode)
        return {
            "ok": True,
            "insights": [
                {k: i[k] for k in ("id", "kind", "text", "quote", "account_name", "meeting_id")}
                for i in self.insights(mission_id)
                if i["status"] in USABLE
            ],
            "outcomes": [
                o.model_dump(mode="json", include={"id", "kind", "account_name", "note"})
                for o in self.wf.outcomes(mission_id)
                if o.mode in modes
            ],
        }

    @guarded
    def propose_lesson(
        self, mission_id: str, text: str, target: str, evidence_ids: list[str]
    ) -> Result:
        """Code checks the evidence. A lesson with one source can be stored but not approved."""
        mission = self.engine.mission(mission_id)
        modes = teach_modes(mission.mode)
        insights = {i["id"]: i for i in self.insights(mission_id) if i["status"] in USABLE}
        outcomes = {o.id: o for o in self.wf.outcomes(mission_id) if o.mode in modes}
        unknown = [e for e in evidence_ids if e not in insights and e not in outcomes]
        if unknown or not evidence_ids:
            return {
                "ok": False,
                "error": "unsupported",
                "message": "unknown evidence",
                "ids": unknown,
            }
        sources = {insights[e]["meeting_id"] for e in evidence_ids if e in insights}
        sources |= {outcomes[e].account_name for e in evidence_ids if e in outcomes}
        rid = stable_id("les", mission_id, text)
        record = {
            "id": rid,
            "text": text,
            "target": target,
            "evidence_ids": evidence_ids,
            "sources": len(sources),
            "single_source": len(sources) < 2,
            "status": "candidate",
            "history": [],
            "mode": modes[0],
            "domain": self._domain(mission_id),
            "strategy_version": None,
            "experiment": None,
        }
        self.engine.save_record("lesson", rid, mission_id, record)
        return {"ok": True, **record}

    @guarded
    def edit_lesson(self, mission_id: str, lesson_id: str, text: str) -> Result:
        lesson = self._lesson(mission_id, lesson_id)
        if lesson is None:
            return {"ok": False, "error": "not_found", "message": lesson_id}
        updated = {**lesson, "text": text, "history": [*lesson["history"], lesson["text"]]}
        self.engine.save_record("lesson", lesson_id, mission_id, updated)
        return {"ok": True}

    @guarded
    def delete_lesson(self, mission_id: str, lesson_id: str) -> Result:
        """The content goes. The row stays so the history still adds up."""
        lesson = self._lesson(mission_id, lesson_id)
        if lesson is None:
            return {"ok": False, "error": "not_found", "message": lesson_id}
        removed = {**lesson, "text": "", "history": [], "status": "deleted"}
        self.engine.save_record("lesson", lesson_id, mission_id, removed)
        return {"ok": True}

    def _start_experiment(self, mission_id: str, change: str, version: int) -> str:
        rid = stable_id("exp", mission_id, change, version)
        record = {
            "id": rid,
            "change": change,
            "version": version,
            "metric": "meetings per message sent",
            "rule": f"At least {MIN_SAMPLE} sends on each side, then keep or roll back",
            "status": "running",
        }
        self.engine.save_record("experiment", rid, mission_id, record)
        return rid

    @guarded
    def decide_lesson(self, mission_id: str, lesson_id: str, decision: str) -> Result:
        lesson = self._lesson(mission_id, lesson_id)
        if lesson is None:
            return {"ok": False, "error": "not_found", "message": lesson_id}
        if decision == "rejected":
            self.engine.save_record(
                "lesson", lesson_id, mission_id, {**lesson, "status": "rejected"}
            )
            return {"ok": True, "status": "rejected"}
        if lesson["single_source"]:
            return {"ok": False, "error": "one_source", "message": "one source is not a pattern"}
        proposal = self.wf.add_proposal(
            mission_id, lesson["text"], f"{lesson['sources']} sources", lesson["evidence_ids"]
        )
        out = self.decide_proposal(mission_id, proposal["id"], "approved", lesson)
        return out

    @guarded
    def decide_proposal(
        self,
        mission_id: str,
        proposal_id: str,
        decision: str,
        lesson: dict[str, Any] | None = None,
    ) -> Result:
        """Approval versions the strategy, makes it a lesson future work receives, and starts
        measuring it. Those three happen together or the change has not really happened."""
        out = self.wf.decide_proposal(mission_id, proposal_id, decision)
        if decision != "approved" or not out.get("ok"):
            return out
        change = next(p for p in self.wf.proposals(mission_id) if p["id"] == proposal_id)
        modes = teach_modes(self.engine.mission(mission_id).mode)
        version = out["version"]
        experiment = self._start_experiment(mission_id, change["change"], version)
        base = lesson or {
            "id": stable_id("les", mission_id, change["change"]),
            "text": change["change"],
            "target": change.get("target", "messaging"),
            "evidence_ids": change["outcome_ids"],
            "sources": len(change["outcome_ids"]),
            "single_source": False,
            "history": [],
            "dimension": change.get("dimension"),
            "value": change.get("value"),
            "mode": modes[0],
            "domain": self._domain(mission_id),
        }
        approved = {
            **base,
            "status": "approved",
            "strategy_version": version,
            "experiment": experiment,
        }
        self.engine.save_record("lesson", approved["id"], mission_id, approved)
        return {**out, "experiment": experiment, "lesson": approved["id"]}

    # ── campaign plans ──────────────────────────────────────────────────────────────────────

    def plans(self, mission_id: str) -> list[dict[str, Any]]:
        return self.engine.records("plan", mission_id)

    @guarded
    def propose_campaign_plan(
        self,
        mission_id: str,
        summary: str,
        changes: list[dict[str, Any]],
        campaign: dict[str, Any],
    ) -> Result:
        """The next campaign as one reviewable decision. Every change must cite real evidence, and
        a pattern needs two independent sources; one source can only be labelled an experiment."""
        mission = self.engine.mission(mission_id)
        if not changes:
            return {"ok": False, "error": "empty_plan", "message": "nothing to change"}
        modes = teach_modes(mission.mode)
        insights = {i["id"]: i for i in self.insights(mission_id) if i["status"] in USABLE}
        outcomes = {o.id: o for o in self.wf.outcomes(mission_id) if o.mode in modes}
        checked = []
        for index, item in enumerate(changes):
            ids = list(item.get("evidence_ids") or [])
            unknown = [e for e in ids if e not in insights and e not in outcomes]
            if unknown or not ids:
                return {"ok": False, "error": "unsupported", "index": index, "ids": unknown}
            sources = {insights[e]["meeting_id"] for e in ids if e in insights}
            sources |= {outcomes[e].account_name for e in ids if e in outcomes}
            experiment = bool(item.get("experiment"))
            if len(sources) < 2 and not experiment:
                return {
                    "ok": False,
                    "error": "one_source",
                    "index": index,
                    "message": "one source is not a pattern; label it an experiment",
                }
            checked.append(
                {
                    "text": str(item["text"]),
                    "target": item.get("target", "messaging"),
                    "evidence_ids": ids,
                    "sources": len(sources),
                    "experiment": experiment,
                    "dimension": item.get("dimension"),
                    "value": item.get("value"),
                }
            )
        rid = stable_id("plan", mission_id, summary, len(self.plans(mission_id)))
        record = {
            "id": rid,
            "summary": summary,
            "changes": checked,
            "campaign": campaign,
            "status": "proposed",
        }
        self.engine.save_record("plan", rid, mission_id, record)
        return {"ok": True, **record}

    @guarded
    def decide_campaign_plan(self, mission_id: str, plan_id: str, decision: str) -> Result:
        """Approval is one strategy version, one experiment, and a lesson for each change that has
        two sources. Experiments are tested, not taught."""
        plan = next((p for p in self.plans(mission_id) if p["id"] == plan_id), None)
        if plan is None:
            return {"ok": False, "error": "not_found", "message": plan_id}
        if plan["status"] != "proposed":
            return {"ok": False, "error": "already_decided", "message": plan["status"]}
        if decision != "approved":
            self.engine.save_record("plan", plan_id, mission_id, {**plan, "status": decision})
            return {"ok": True, "status": decision}
        texts = [c["text"] for c in plan["changes"]]
        made = self.wf.version_strategy(
            mission_id, texts, {"next_campaign": {**plan["campaign"], "plan": plan_id}}
        )
        if not made["ok"]:
            return made
        version = made["version"]
        experiment = self._start_experiment(mission_id, plan["summary"], version)
        modes = teach_modes(self.engine.mission(mission_id).mode)
        for c in plan["changes"]:
            if c["experiment"]:
                continue
            lid = stable_id("les", mission_id, c["text"])
            self.engine.save_record(
                "lesson",
                lid,
                mission_id,
                {
                    "id": lid,
                    "text": c["text"],
                    "target": c["target"],
                    "evidence_ids": c["evidence_ids"],
                    "sources": c["sources"],
                    "single_source": False,
                    "status": "approved",
                    "history": [],
                    "dimension": c["dimension"],
                    "value": c["value"],
                    "mode": modes[0],
                    "domain": self._domain(mission_id),
                    "strategy_version": version,
                    "experiment": experiment,
                },
            )
        self.engine.save_record(
            "plan", plan_id, mission_id, {**plan, "status": "approved", "version": version}
        )
        return {"ok": True, "status": "approved", "version": version, "experiment": experiment}

    def _measured(self, mission_id: str, record: dict[str, Any]) -> dict[str, Any]:
        modes = teach_modes(self.engine.mission(mission_id).mode)
        result = measure_experiment(
            record["version"],
            self.touches(mission_id),
            self.wf.outcomes(mission_id),
            self.wf.today(),
            modes,
        )
        return {**record, "result": result}

    def experiments(self, mission_id: str) -> list[dict[str, Any]]:
        return [
            self._measured(mission_id, e) for e in self.engine.records("experiment", mission_id)
        ]

    def _retire(self, mission_id: str, after_version: int) -> None:
        for lesson in self.lessons(mission_id):
            if lesson["status"] == "approved" and lesson["strategy_version"] > after_version:
                self.engine.save_record(
                    "lesson", lesson["id"], mission_id, {**lesson, "status": "retired"}
                )
        for e in self.engine.records("experiment", mission_id):
            if e["status"] == "running" and e["version"] > after_version:
                self.engine.save_record(
                    "experiment", e["id"], mission_id, {**e, "status": "rolled_back"}
                )

    @guarded
    def rollback(self, mission_id: str, version: int) -> Result:
        """Restores the version and stops what came after it, so old guidance stops being used."""
        out = self.wf.rollback_strategy(mission_id, version)
        if out.get("ok"):
            self._retire(mission_id, version)
        return out

    @guarded
    def conclude_experiment(self, mission_id: str, experiment_id: str, decision: str) -> Result:
        """Step nine. The numbers advise, a person decides, and it needs a real result."""
        record = next((e for e in self.experiments(mission_id) if e["id"] == experiment_id), None)
        if record is None:
            return {"ok": False, "error": "not_found", "message": experiment_id}
        if record["status"] != "running":
            return {"ok": False, "error": "already_decided", "message": record["status"]}
        if record["result"]["verdict"] == "insufficient":
            return {"ok": False, "error": "insufficient", "message": "not enough results yet"}
        if decision == "roll_back":
            return self.rollback(mission_id, record["version"] - 1)
        stored = {k: v for k, v in record.items() if k != "result"}
        self.engine.save_record(
            "experiment", experiment_id, mission_id, {**stored, "status": "kept"}
        )
        return {"ok": True, "status": "kept"}

    # ── demo and the page ───────────────────────────────────────────────────────────────────

    @guarded
    def seed_demo(self, mission_id: str) -> Result:
        """Fixture missions only: labelled results that let the whole loop be seen working."""
        mission = self.engine.mission(mission_id)
        if mission.mode != "replay":
            return {"ok": False, "error": "not_fixture", "message": "only on a fixture mission"}
        version = self.wf.strategy_version(mission_id)
        batch = len(self.engine.records("touch", mission_id))
        sent_on = self.wf.today() - timedelta(days=30)
        for audience, wins in DEMO_TOUCHES:
            for i in range(MIN_SAMPLE):
                rid = f"demo_{mission_id}_{batch}_{audience}_{i}"
                name = f"Demo {audience} {batch + i}"
                touch = Touch(
                    id=rid,
                    account_name=name,
                    audience=audience,
                    signal_types=DEMO_SIGNALS[audience],
                    strategy_version=version,
                    sent_on=sent_on,
                    mode="replay",
                )
                self.engine.save_record("touch", rid, mission_id, touch.model_dump(mode="json"))
                if i < wins:
                    self.wf.record_outcome(
                        mission_id,
                        {
                            "kind": "meeting_booked",
                            "occurred_on": sent_on.isoformat(),
                            "account_name": name,
                            "outreach_id": rid,
                            "source": "demo",
                        },
                    )
        return {"ok": True}

    def view(self, mission_id: str) -> dict[str, Any]:
        mission = self.engine.mission(mission_id)
        modes = teach_modes(mission.mode)
        replies = self.replies(mission_id)
        meetings = self.wf.meetings(mission_id)
        touches = self.touches(mission_id)
        report = compare(touches, self.wf.outcomes(mission_id), self.wf.today(), modes)
        insights = self.insights(mission_id)
        lessons = [x for x in self.lessons(mission_id) if x["status"] != "deleted"]
        experiments = self.experiments(mission_id)
        decisions = self.wf.proposals(mission_id)
        versions = self.wf.strategy_versions(mission_id)
        decided = [d for d in decisions if d["status"] != "proposed"]
        return {
            "demo": mission.mode == "replay",
            "replies": replies,
            "suppressions": self.suppressions(mission_id),
            "lifecycle": {
                o["id"]: lifecycle(
                    o,
                    [r for r in replies if r["outreach_id"] == o["id"]],
                    [m for m in meetings if m.get("account_name") == o["target_name"]],
                )
                for o in self.wf.outreach(mission_id)
            },
            "insights": insights,
            "lessons": lessons,
            "experiments": experiments,
            "report": report,
            "decisions": decisions,
            "plans": self.plans(mission_id),
            "timeline": [
                {
                    "version": v["version"],
                    "author": v["author"],
                    "changes": v["changes"],
                    "rolled_back_to": v.get("rolled_back_to"),
                    "guidance": v["body"].get("guidance", []),
                }
                for v in versions
            ],
            "steps": [
                {"name": "Capture", "count": len(replies) + len(meetings)},
                {
                    "name": "Link",
                    "count": sum(1 for o in self.wf.outcomes(mission_id) if o.outreach_id),
                },
                {
                    "name": "Extract",
                    "count": sum(1 for i in insights if i["status"] in USABLE) + len(lessons),
                },
                {"name": "Check", "count": report["counted"]},
                {"name": "Propose", "count": len(report["proposals"]) + len(lessons)},
                {"name": "Approve", "count": len(decided)},
                {"name": "Version", "count": max(len(versions) - 1, 0)},
                {
                    "name": "Measure",
                    "count": sum(
                        1 for e in experiments if e["result"]["verdict"] != "insufficient"
                    ),
                },
                {
                    "name": "Keep or roll back",
                    "count": sum(1 for e in experiments if e["status"] != "running"),
                },
            ],
        }
