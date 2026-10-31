"""Autopilot's driver: decides who to contact and moves each message toward a scheduled send.

One effect per mission per tick, and every step is derived from stored state (a target exists, an
outreach exists, a schedule exists), so a restart or a second tick repeats nothing. Anything it
cannot do is logged once with the reason and left for the founder. It never sends: scheduled sends
reach Gmail through the Director, and Gmail's send is answered by the policy in `autopilot.py`."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from trigger_point.api.app import Services
from trigger_point.office.autopilot import AutopilotService, Availability, Policy
from trigger_point.office.conversations import Conversations
from trigger_point.office.store import OfficeStore
from trigger_point.workflow.conversation import OPEN_STATES
from trigger_point.workflow.models import TERMINAL

STOPPED = TERMINAL - {"COMPLETE"}
from trigger_point.workflow.service import audience_for

LEAD = timedelta(minutes=2)
BREAKER = 3  # held steps before a mission is paused for the founder to look
_locks: dict[str, threading.Lock] = {}


def next_send_time(window: Availability, now: datetime) -> datetime:
    """The first moment at or after now + LEAD that falls inside the send window."""
    tz = ZoneInfo(window.timezone)
    t = (now + LEAD).astimezone(tz).replace(second=0, microsecond=0)
    for _ in range(8 * 24 * 60 // 15):  # at most a week, in 15 minute steps
        if window.allows(t):
            return t
        t = (t + timedelta(minutes=15)).replace(second=0, microsecond=0)
    return t  # no window opens in a week: the schedule step will be refused as unusable


def _once(
    office: OfficeStore, mission: str, kind: str, subject: str, decision: str, reason: str
) -> bool:
    """Logs a driver step once. False means it was already logged and nothing should repeat."""
    if office.autopilot_logged(mission, kind, subject):
        return False
    office.log_autopilot(mission, kind, decision, reason, subject=subject)
    return True


def drive_mission(
    services: Services,
    office: OfficeStore,
    policy: Policy,
    mission_id: str,
    convs: Conversations | None = None,
) -> str | None:
    """Does the single next thing for one mission. Returns what it did, or None."""
    wf, fb = services.workflow, services.feedback
    m = wf.engine.mission(mission_id)
    # COMPLETE means the Director's own pipeline finished; outreach and replies come after it.
    if m.state in STOPPED or m.research_id is None:
        return None
    if convs is not None:
        read = convs.process(mission_id, policy)
        if read:
            return read
    targets = [t for t in wf.targets(mission_id) if t.get("source") == "discovered"]
    outreach = wf.outreach(mission_id)

    # 1. Who to contact: the best qualified accounts that have a named buyer.
    if not targets:
        run = services.store.get_research(m.research_id)
        if run is None:
            return None
        ranked = sorted(
            (a for a in run.accounts if a.score.status == "qualified"),
            key=lambda a: a.score.total,
            reverse=True,
        )
        made: list[str] = []
        for ar in ranked:
            if len(made) >= policy.meetings_wanted:
                break
            if ar.best_person is None or not ar.best_person.person.name:
                _once(
                    office,
                    mission_id,
                    "target",
                    f"nobuyer:{ar.account.provider_company_id}",
                    "hold",
                    f"No named buyer found at {ar.account.name}",
                )
                continue
            out = wf.target_from_account(
                mission_id, ar.account.provider_company_id, audience_for(ar.account.industries)
            )
            if out.get("ok"):
                made.append(str(out["name"]))
        if made:
            office.log_autopilot(
                mission_id, "target", "allow", f"Chose {len(made)} people to contact", "targets"
            )
            return f"targets:{len(made)}"
        return None

    # 2. Write one message for each target that has none.
    written = {o["target_id"] for o in outreach}
    for t in targets:
        if t["id"] in written or wf.is_suppressed(mission_id, t["id"]):
            continue
        out = wf.write_outreach(mission_id, t["id"])
        if out.get("ok"):
            office.log_autopilot(mission_id, "write", "allow", f"Wrote to {t['name']}", t["id"])
            return f"write:{t['id']}"
        if _once(office, mission_id, "write", t["id"], "hold", str(out.get("message") or out)):
            return f"hold:write:{t['id']}"
        return None

    # 3. Approve a message that passed every check, and 4. schedule it.
    for o in outreach:
        sent = o.get("test_sends") or o.get("manual_sends")
        if sent or o.get("schedule"):
            continue
        if o["status"] == "verified":
            if not policy.auto_approve_outreach:
                continue
            out = wf.approve_outreach(mission_id, o["id"], o["content_hash"])
            if out.get("ok"):
                office.log_autopilot(
                    mission_id,
                    "approve",
                    "allow",
                    f"Approved the message to {o['target_name']}",
                    o["id"],
                )
                return f"approve:{o['id']}"
            _once(office, mission_id, "approve", o["id"], "hold", str(out.get("message") or out))
            return None
        if o["status"] == "approved":
            scheduled_today = _scheduled_today(office, mission_id, fb.now())
            if scheduled_today >= policy.daily_send_cap:
                return None
            when = next_send_time(policy.send_window, fb.now())
            out = fb.schedule_send(
                mission_id,
                o["id"],
                when.replace(tzinfo=None).isoformat(),
                policy.send_window.timezone,
            )
            if out.get("ok"):
                office.log_autopilot(
                    mission_id,
                    "schedule",
                    "allow",
                    f"Scheduled the message to {o['target_name']} for {when:%a %H:%M}",
                    o["id"],
                )
                return f"schedule:{o['id']}"
            _once(office, mission_id, "schedule", o["id"], "hold", str(out.get("message") or out))
            return None
        _once(
            office,
            mission_id,
            "write",
            f"{o['id']}:{o['status']}",
            "hold",
            f"The message to {o['target_name']} did not pass its checks",
        )
    return None


def _scheduled_today(office: OfficeStore, mission_id: str, now: datetime) -> int:
    day = now.date().isoformat()
    return sum(
        1
        for e in office.autopilot_log(mission_id, 500)
        if e["kind"] == "schedule" and e["decision"] == "allow" and e["at"][:10] == day
    )


def drive(
    services: Services,
    office: OfficeStore,
    autopilot: AutopilotService,
    convs: Conversations | None = None,
    runner: Any = None,
) -> list[str]:
    """One pass over every mission. A failure in one mission never stops the others."""
    done: list[str] = []
    for m in services.workflow.engine.missions(limit=50):
        policy = autopilot.policy_for(m.id)
        if not policy.active:
            continue
        lock = _locks.setdefault(m.id, threading.Lock())
        if not lock.acquire(blocking=False):
            continue
        try:
            effect = drive_mission(services, office, policy, m.id, convs)
            if convs is not None and runner is not None:
                nudge(office, convs, runner, m.id, services.feedback.now())
            if effect:
                done.append(f"{m.id}:{effect}")
            _trip_breaker(office, autopilot, m.id)
        except Exception as exc:  # noqa: BLE001 - one bad mission must not stop the scheduler
            _once(
                office,
                m.id,
                "error",
                type(exc).__name__,
                "hold",
                f"Autopilot stopped a step: {exc}",
            )
        finally:
            lock.release()
    return done


def _trip_breaker(office: OfficeStore, autopilot: AutopilotService, mission_id: str) -> None:
    """Several held steps means something is wrong: pause and let the founder look."""
    holds: list[Any] = []
    for e in office.autopilot_log(mission_id, 200):  # newest first; a pause starts a fresh count
        if e["kind"] == "control":
            break
        if e["decision"] == "hold" and e["kind"] in ("write", "approve", "schedule", "error"):
            holds.append(e)
    if len(holds) >= BREAKER and autopilot.policy_for(mission_id).active:
        autopilot.save(mission_id, {"paused": True})
        office.log_autopilot(
            mission_id, "control", "hold", f"Paused after {len(holds)} steps could not finish"
        )


REPLY_CHECK = timedelta(minutes=10)
CALENDAR_ASK = timedelta(minutes=5)


def nudge(
    office: OfficeStore, convs: Conversations, runner: Any, mission_id: str, now: datetime
) -> None:
    """Asks the Director for the connector work only it can do: send a reply, make the calendar
    event, read new mail. Each ask is made once, and never while the Director is busy."""
    run = office.run(mission_id)
    if run is not None and run["status"] == "working":
        return
    if convs.needs_calendar(mission_id):
        last_cal = next(
            (e for e in office.autopilot_log(mission_id, 100) if e["kind"] == "calendar"), None
        )
        if last_cal is None or now - datetime.fromisoformat(last_cal["at"]) > CALENDAR_ASK:
            office.log_autopilot(mission_id, "calendar", "allow", "Checking your calendar")
            runner.send(
                mission_id,
                "Read my Google Calendar for the next 14 days, every calendar I own. Then call "
                "record_busy_times with every event as {start, end} in ISO 8601 with a UTC offset, "
                "including all-day and tentative events.",
            )
        return
    for conv in convs.all(mission_id):
        box = conv.get("outbox")
        if box and not box["sent"]:
            subject = f"out:{conv['id']}:{len(conv['turns'])}:{box['kind']}"
            if _once(office, mission_id, "nudge", subject, "allow", "Asked to send the reply"):
                runner.send(
                    mission_id,
                    f"Send the waiting reply for target_id {conv['target_id']}: call prepare_reply, "
                    "send exactly that with Gmail send_message (to, subject, body, replyThreadId), "
                    "then call record_reply_sent with the Gmail message id.",
                )
                return
        if conv["state"] == "booking" and conv["token"]:  # noqa: SIM102
            if _once(
                office, mission_id, "nudge", f"book:{conv['token']}", "allow", "Asked to book"
            ):
                runner.send(
                    mission_id,
                    f"Book the meeting for target_id {conv['target_id']}: call get_booking, create "
                    "exactly that Google Calendar event with a Google Meet link and the attendee "
                    "invited, then call record_booked_meeting with the token, the event id and the "
                    "Meet link.",
                )
                return
    open_threads = [
        o
        for o in convs.wf.outreach(mission_id)
        if o.get("test_sends")
        and ((c := convs.get(mission_id, o["target_id"])) is None or c["state"] in OPEN_STATES)
    ]
    if not open_threads:
        return
    last = next((e for e in office.autopilot_log(mission_id, 100) if e["kind"] == "check"), None)
    if last is None or now - datetime.fromisoformat(last["at"]) > REPLY_CHECK:
        office.log_autopilot(mission_id, "check", "allow", "Checking for replies")
        runner.send(
            mission_id,
            "Check for replies: call list_open_threads, read each thread with Gmail get_thread "
            "(PLAIN_TEXT), then call sync_replies.",
        )
