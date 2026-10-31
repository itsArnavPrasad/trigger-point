"""The Office API. Loopback only, token required, and the only write path into a mission.

Approve and deny answer the Claude Code permission prompt held by the hook. Nothing here can run
a gated tool: the human's answer goes to Claude Code, and Claude Code runs the tool."""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import time
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from trigger_point.api.app import Services
from trigger_point.office import scheduler
from trigger_point.office.connectors import ConnectorStatus
from trigger_point.office.runner import PROJECT_ROOT, MissionRunner
from trigger_point.office.store import OfficeStore
from trigger_point.office.views import (
    harness_connectors,
    integration_health,
    mission_summary,
    mission_view,
    prompt_versions,
    stakeholder_role,
)
from trigger_point.workflow.engine import MissionNotFound

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
POLL_SECONDS = 0.4
HOLD_SECONDS = 25.0
MISSION_ID = re.compile(r"wm_[0-9a-f]{16}")
__all__ = ["install_office", "office_token", "stakeholder_role"]


def trigger_point_home() -> Path:
    return Path(os.environ.get("TRIGGER_POINT_HOME") or Path.home() / ".trigger-point")


def office_token() -> str:
    """Created once, readable only by this user. Hooks read the same file."""
    home = trigger_point_home()
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = home / "office-token"
    if not path.exists():
        path.touch(mode=0o600)
        path.write_text(secrets.token_hex(32))
    path.chmod(0o600)
    return path.read_text().strip()


class NewMission(BaseModel):
    website_url: str = Field(min_length=3, max_length=300)
    goal: str = Field(min_length=3, max_length=500)
    product_description: str = Field(default="", max_length=2000)
    target_geography: str = Field(default="", max_length=200)
    time_horizon: str = Field(default="", max_length=100)


class Chat(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class Decision(BaseModel):
    decision: str = Field(pattern="^(allow|deny)$")
    message: str | None = Field(default=None, max_length=500)


class ProfileEdit(BaseModel):
    field: str = Field(max_length=40)
    values: list[str] = Field(max_length=50)


class IcpEdit(BaseModel):
    changes: dict[str, Any]
    rationale: str = Field(min_length=3, max_length=300)


class Fields(BaseModel):
    fields: dict[str, Any]


class OutreachEdit(BaseModel):
    subject: str = Field(max_length=200)
    body: str = Field(max_length=4000)


class Approve(BaseModel):
    content_hash: str = Field(min_length=64, max_length=64)


class Decide(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")


class HookCapture(BaseModel):
    tool: str = Field(max_length=120)
    tool_input: dict[str, Any] = Field(default_factory=dict)
    tool_response: Any = None
    mission_id: str | None = None
    session_id: str | None = None


class Schedule(BaseModel):
    send_at: str = Field(max_length=40)
    timezone: str = Field(max_length=60)


class Action(BaseModel):
    action: str = Field(pattern="^(confirm|reject|correct)$")
    text: str | None = Field(default=None, max_length=2000)


class Text(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class Label(BaseModel):
    label: str = Field(pattern="^(positive|negative|opted_out)$")


class Progress(BaseModel):
    progress: str = Field(pattern="^(progressed|stalled|disqualified)$")


class Conclude(BaseModel):
    decision: str = Field(pattern="^(keep|roll_back)$")


class Proposal(BaseModel):
    change: str = Field(min_length=3, max_length=300)
    evidence: str = Field(min_length=3, max_length=1000)
    outcome_ids: list[str] = Field(default_factory=list, max_length=500)
    dimension: str | None = Field(default=None, pattern="^[a-z_]{1,40}$")
    value: str | None = Field(default=None, pattern="^[A-Za-z0-9_ .-]{1,60}$")


class AudiencePick(BaseModel):
    audience: str = Field(min_length=1, max_length=40, pattern="^[a-z_]+$")


class HookEvent(BaseModel):
    kind: str = Field(max_length=40)
    summary: str = Field(max_length=240)
    mission_id: str | None = None
    session_id: str | None = None
    agent_id: str | None = None
    role: str | None = None
    tool: str | None = Field(default=None, max_length=120)


class HookPermission(BaseModel):
    tool: str = Field(max_length=120)
    tool_input: dict[str, Any] = Field(default_factory=dict)
    mission_id: str | None = None
    session_id: str | None = None
    role: str | None = None


def _first_prompt(m: NewMission) -> str:
    """User text is passed as labelled data, and the tool validates it."""
    return (
        "Start this Trigger Point mission now. Call create_mission with exactly these values.\n"
        + json.dumps(m.model_dump(), indent=2)
    )


def office_router(services: Services, office: OfficeStore, runner: MissionRunner) -> APIRouter:  # noqa: C901
    token = office_token()
    connectors = ConnectorStatus()

    def need_token(authorization: str = Header(default="")) -> None:
        if not hmac.compare_digest(authorization.encode(), f"Bearer {token}".encode()):
            raise HTTPException(401, "office token required")

    r = APIRouter(prefix="/api/office", dependencies=[Depends(need_token)])

    def known(mission_id: str) -> None:
        try:
            services.workflow.engine.mission(mission_id)
        except MissionNotFound as exc:
            raise HTTPException(404, "unknown mission") from exc

    @r.get("/bootstrap")
    def bootstrap() -> dict[str, Any]:
        s = services.settings
        return {
            "missions": mission_summary(services),
            "health": integration_health(services, connectors.states()),
            "harness": harness_connectors(connectors.states()),
            "prompts": prompt_versions(),
            "mode": s.run_mode,
            "provider_modes": dict(s.provider_modes),
        }

    @r.post("/missions", status_code=201)
    def start_mission(body: NewMission) -> dict[str, Any]:
        s = services.settings
        engine = services.workflow.engine
        missing = services.workflow.fixture_problem(body.website_url)
        if missing:
            raise HTTPException(409, missing)
        # The record exists at once, so the page has something to open. The Director then calls
        # create_mission with the same website and goal, which finds it and reads the site.
        m = engine.create_mission(body.website_url, body.goal, s.run_mode, dict(s.provider_modes))
        office.add_message(m.id, "user", f"{body.website_url}: {body.goal}")
        runner.send(m.id, _first_prompt(body))
        return {"mission_id": m.id}

    @r.get("/missions/{mission_id}")
    def get_mission(mission_id: str) -> dict[str, Any]:
        known(mission_id)
        return {
            **mission_view(services, office, mission_id),
            "running": runner.is_running(mission_id),
        }

    @r.post("/missions/{mission_id}/messages", status_code=202)
    def post_message(mission_id: str, body: Chat) -> dict[str, bool]:
        known(mission_id)
        office.add_message(mission_id, "user", body.text)
        runner.send(mission_id, body.text)
        return {"ok": True}

    @r.post("/missions/{mission_id}/cancel")
    def cancel(mission_id: str) -> dict[str, Any]:
        known(mission_id)
        runner.stop(mission_id)
        for p in office.pending_permissions(mission_id):
            office.decide_permission(p["id"], "deny", "The mission was cancelled.")
        out = services.workflow.cancel_mission(mission_id, "Cancelled in the Office")
        office.touch(mission_id)
        return out

    @r.post("/missions/{mission_id}/profile")
    def edit_profile(mission_id: str, body: ProfileEdit) -> dict[str, Any]:
        known(mission_id)
        out = services.workflow.edit_business_profile(mission_id, body.field, body.values)
        if not out.get("ok"):
            raise HTTPException(409, str(out.get("message")))
        office.touch(mission_id)
        return out

    @r.post("/missions/{mission_id}/icp")
    def edit_icp(mission_id: str, body: IcpEdit) -> dict[str, Any]:
        known(mission_id)
        out = services.workflow.edit_icp(mission_id, body.changes, body.rationale)
        if not out.get("ok"):
            raise HTTPException(409, str(out.get("message")))
        office.touch(mission_id)
        return out

    def done(mission_id: str, out: dict[str, Any]) -> dict[str, Any]:
        if out.get("ok") is False:
            raise HTTPException(409, str(out.get("message") or out.get("error")))
        office.touch(mission_id)
        return out

    @r.post("/missions/{mission_id}/samples", status_code=201)
    def add_samples(mission_id: str) -> dict[str, Any]:
        known(mission_id)
        return done(mission_id, services.workflow.add_sample_targets(mission_id))

    @r.post("/missions/{mission_id}/outreach/{outreach_id}/test-send", status_code=202)
    def test_send(mission_id: str, outreach_id: str) -> dict[str, Any]:
        """Asks the Director. Gmail's send is then held in the Office for a click."""
        known(mission_id)
        prepared = services.workflow.prepare_test_send(mission_id, outreach_id)
        if not prepared.get("ok"):
            raise HTTPException(409, str(prepared.get("message")))
        office.add_message(mission_id, "user", "Send this message to the test inbox.")
        runner.send(mission_id, f"Send a test email for outreach_id {outreach_id}.")
        return {"ok": True}

    @r.post("/missions/{mission_id}/test-meeting", status_code=202)
    def test_meeting(mission_id: str) -> dict[str, Any]:
        known(mission_id)
        office.add_message(mission_id, "user", "Book a test meeting.")
        runner.send(mission_id, "Book a 30 minute test meeting next week with the test inbox.")
        return {"ok": True}

    @r.post("/missions/{mission_id}/targets", status_code=201)
    def add_target(mission_id: str, body: Fields) -> dict[str, Any]:
        known(mission_id)
        return done(mission_id, services.workflow.add_target(mission_id, body.fields))

    @r.post("/missions/{mission_id}/targets/{target_id}/write", status_code=201)
    def write_outreach(mission_id: str, target_id: str) -> dict[str, Any]:
        known(mission_id)
        return done(mission_id, services.workflow.write_outreach(mission_id, target_id))

    @r.post("/missions/{mission_id}/outreach/{outreach_id}")
    def edit_outreach(mission_id: str, outreach_id: str, body: OutreachEdit) -> dict[str, Any]:
        known(mission_id)
        out = services.workflow.edit_outreach(mission_id, outreach_id, body.subject, body.body)
        return done(mission_id, out)

    @r.post("/missions/{mission_id}/outreach/{outreach_id}/approve")
    def approve_outreach(mission_id: str, outreach_id: str, body: Approve) -> dict[str, Any]:
        known(mission_id)
        out = services.workflow.approve_outreach(mission_id, outreach_id, body.content_hash)
        return done(mission_id, out)

    @r.post("/missions/{mission_id}/outcomes", status_code=201)
    def add_outcome(mission_id: str, body: Fields) -> dict[str, Any]:
        known(mission_id)
        return done(mission_id, services.workflow.record_outcome(mission_id, body.fields))

    @r.post("/missions/{mission_id}/meetings", status_code=201)
    def add_meeting(mission_id: str, body: Fields) -> dict[str, Any]:
        known(mission_id)
        return done(mission_id, services.workflow.add_meeting(mission_id, body.fields))

    @r.post("/missions/{mission_id}/costs", status_code=201)
    def add_cost(mission_id: str, body: Fields) -> dict[str, Any]:
        known(mission_id)
        return done(mission_id, services.workflow.add_cost(mission_id, body.fields))

    @r.post("/missions/{mission_id}/accounts/{account_id}/target", status_code=201)
    def target_from_account(mission_id: str, account_id: int, body: AudiencePick) -> dict[str, Any]:
        """A researched, qualified account as an outreach target. A rejected one is refused."""
        known(mission_id)
        return done(
            mission_id, services.workflow.target_from_account(mission_id, account_id, body.audience)
        )

    @r.post("/missions/{mission_id}/proposals", status_code=201)
    def add_proposal(mission_id: str, body: Proposal) -> dict[str, Any]:
        known(mission_id)
        out = services.workflow.add_proposal(
            mission_id, body.change, body.evidence, body.outcome_ids, body.dimension, body.value
        )
        return done(mission_id, out)

    @r.post("/missions/{mission_id}/proposals/{proposal_id}")
    def decide_proposal(mission_id: str, proposal_id: str, body: Decide) -> dict[str, Any]:
        known(mission_id)
        out = services.feedback.decide_proposal(mission_id, proposal_id, body.decision)
        return done(mission_id, out)

    @r.post("/missions/{mission_id}/strategy/{version}/rollback")
    def rollback(mission_id: str, version: int) -> dict[str, Any]:
        known(mission_id)
        return done(mission_id, services.feedback.rollback(mission_id, version))

    fb = services.feedback

    def director(mission_id: str, shown: str, instruction: str) -> dict[str, bool]:
        known(mission_id)
        office.add_message(mission_id, "user", shown)
        runner.send(mission_id, instruction)
        return {"ok": True}

    @r.post("/missions/{mission_id}/check-replies", status_code=202)
    def check_replies(mission_id: str) -> dict[str, bool]:
        return director(mission_id, "Check for replies.", "Check for replies.")

    @r.post("/missions/{mission_id}/import-meetings", status_code=202)
    def import_meetings(mission_id: str) -> dict[str, bool]:
        return director(
            mission_id, "Import meetings from Wispr Flow.", "Import meetings from Wispr Flow."
        )

    @r.post("/missions/{mission_id}/plan-campaign", status_code=202)
    def plan_campaign(mission_id: str) -> dict[str, bool]:
        return director(mission_id, "Plan the next campaign.", "Plan the next campaign.")

    @r.post("/missions/{mission_id}/review-learning", status_code=202)
    def review_learning(mission_id: str) -> dict[str, bool]:
        return director(mission_id, "Review what we learned.", "Review what we learned.")

    @r.post("/missions/{mission_id}/outreach/{outreach_id}/schedule")
    def schedule(mission_id: str, outreach_id: str, body: Schedule) -> dict[str, Any]:
        known(mission_id)
        return done(
            mission_id, fb.schedule_send(mission_id, outreach_id, body.send_at, body.timezone)
        )

    @r.post("/missions/{mission_id}/outreach/{outreach_id}/cancel-schedule")
    def cancel_schedule(mission_id: str, outreach_id: str) -> dict[str, Any]:
        known(mission_id)
        return done(mission_id, fb.cancel_schedule(mission_id, outreach_id))

    @r.post("/missions/{mission_id}/outreach/{outreach_id}/follow-up", status_code=201)
    def follow_up(mission_id: str, outreach_id: str) -> dict[str, Any]:
        known(mission_id)
        return done(mission_id, fb.write_follow_up(mission_id, outreach_id))

    @r.post("/missions/{mission_id}/outreach/{outreach_id}/mark-sent")
    def mark_sent(mission_id: str, outreach_id: str, body: Text) -> dict[str, Any]:
        known(mission_id)
        return done(mission_id, fb.mark_sent(mission_id, outreach_id, body.text))

    @r.post("/missions/{mission_id}/targets/{target_id}/suppress")
    def suppress(mission_id: str, target_id: str, body: Text) -> dict[str, Any]:
        known(mission_id)
        return done(mission_id, fb.suppress(mission_id, target_id, body.text))

    @r.post("/missions/{mission_id}/replies/{reply_id}")
    def label_reply(mission_id: str, reply_id: str, body: Label) -> dict[str, Any]:
        known(mission_id)
        return done(mission_id, fb.label_reply(mission_id, reply_id, body.label))

    @r.post("/missions/{mission_id}/meetings/{meeting_id}/link")
    def link_meeting(mission_id: str, meeting_id: str, body: Text) -> dict[str, Any]:
        known(mission_id)
        return done(mission_id, fb.link_meeting(mission_id, meeting_id, body.text))

    @r.post("/missions/{mission_id}/meetings/{meeting_id}/progress")
    def meeting_progress(mission_id: str, meeting_id: str, body: Progress) -> dict[str, Any]:
        known(mission_id)
        return done(mission_id, fb.set_progress(mission_id, meeting_id, body.progress))

    @r.post("/missions/{mission_id}/insights/{insight_id}")
    def review_insight(mission_id: str, insight_id: str, body: Action) -> dict[str, Any]:
        known(mission_id)
        return done(mission_id, fb.review_insight(mission_id, insight_id, body.action, body.text))

    @r.post("/missions/{mission_id}/lessons/{lesson_id}/decide")
    def decide_lesson(mission_id: str, lesson_id: str, body: Decide) -> dict[str, Any]:
        known(mission_id)
        return done(mission_id, fb.decide_lesson(mission_id, lesson_id, body.decision))

    @r.post("/missions/{mission_id}/plans/{plan_id}/decide")
    def decide_plan(mission_id: str, plan_id: str, body: Decide) -> dict[str, Any]:
        known(mission_id)
        return done(mission_id, fb.decide_campaign_plan(mission_id, plan_id, body.decision))

    @r.post("/missions/{mission_id}/lessons/{lesson_id}/edit")
    def edit_lesson(mission_id: str, lesson_id: str, body: Text) -> dict[str, Any]:
        known(mission_id)
        return done(mission_id, fb.edit_lesson(mission_id, lesson_id, body.text))

    @r.post("/missions/{mission_id}/lessons/{lesson_id}/delete")
    def delete_lesson(mission_id: str, lesson_id: str) -> dict[str, Any]:
        known(mission_id)
        return done(mission_id, fb.delete_lesson(mission_id, lesson_id))

    @r.post("/missions/{mission_id}/experiments/{experiment_id}")
    def conclude(mission_id: str, experiment_id: str, body: Conclude) -> dict[str, Any]:
        known(mission_id)
        return done(mission_id, fb.conclude_experiment(mission_id, experiment_id, body.decision))

    @r.post("/missions/{mission_id}/demo-results", status_code=201)
    def demo_results(mission_id: str) -> dict[str, Any]:
        known(mission_id)
        return done(mission_id, fb.seed_demo(mission_id))

    @r.post("/hook/capture", status_code=202)
    def hook_capture(body: HookCapture) -> dict[str, Any]:
        mission = body.mission_id
        if not mission and body.session_id:
            mission = office.mission_for_session(body.session_id)
        if not (mission and MISSION_ID.fullmatch(mission)):
            return {"ok": False, "error": "no_mission"}
        out = fb.capture(mission, body.tool, body.tool_input, body.tool_response)
        office.touch(mission)
        return out

    @r.post("/permissions/{permission_id}")
    def answer(permission_id: str, body: Decision) -> dict[str, bool]:
        if office.permission(permission_id) is None:
            raise HTTPException(404, "unknown permission")
        return {"ok": office.decide_permission(permission_id, body.decision, body.message)}

    @r.post("/hook/event", status_code=202)
    def hook_event(body: HookEvent) -> dict[str, bool]:
        mission = body.mission_id
        if not (mission and MISSION_ID.fullmatch(mission)):
            mission = office.mission_for_session(body.session_id) if body.session_id else None
        office.add_activity(**{**body.model_dump(), "mission_id": mission})
        return {"ok": True}

    @r.post("/hook/permission", status_code=201)
    def hook_permission(body: HookPermission) -> dict[str, str]:
        mission = body.mission_id
        if not mission and body.session_id:
            mission = office.mission_for_session(body.session_id)
        pid = office.open_permission(
            mission, body.session_id, body.role, body.tool, body.tool_input
        )
        return {"id": pid}

    @r.get("/hook/permission/{permission_id}")
    def hook_poll(permission_id: str) -> dict[str, Any]:
        """Holds the call open so the hook is not polling hard. Pending is a valid answer."""
        end = time.monotonic() + HOLD_SECONDS
        while time.monotonic() < end:
            p = office.permission(permission_id)
            if p is None:
                raise HTTPException(404, "unknown permission")
            if p["status"] != "pending":
                return {"status": p["status"], "message": p["message"]}
            time.sleep(POLL_SECONDS)
        return {"status": "pending", "message": None}

    @r.get("/stream")
    def stream() -> StreamingResponse:
        def ticks() -> Iterator[str]:
            last = -1
            beat = 0.0
            while True:
                now = office.latest_change()
                if now != last:
                    last = now
                    yield f"data: {now}\n\n"
                elif time.monotonic() - beat > 10:
                    beat = time.monotonic()
                    yield ": alive\n\n"
                time.sleep(POLL_SECONDS)

        return StreamingResponse(ticks(), media_type="text/event-stream")

    return r


def install_office(app: FastAPI, services: Services, runner: MissionRunner | None = None) -> None:
    """Adds the API, the guards and the built UI."""
    office = OfficeStore(services.store.path)
    active = runner or MissionRunner(office)
    token = office_token()
    app.state.office = office
    app.state.runner = active
    app.include_router(office_router(services, office, active))
    if runner is None:
        scheduler.start(services.feedback, active)

    @app.middleware("http")
    async def guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
        if host not in LOOPBACK:
            return Response("forbidden host", status_code=421)
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).hostname not in LOOPBACK:
            return Response("forbidden origin", status_code=403)
        path = request.url.path
        if path.startswith("/api/") and not path.startswith("/api/office/"):
            supplied = request.headers.get("authorization", "")
            if not hmac.compare_digest(supplied.encode(), f"Bearer {token}".encode()):
                return Response("office token required", status_code=401)
        return await call_next(request)

    dist = PROJECT_ROOT / "office" / "dist"
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
        app.mount("/art", StaticFiles(directory=dist / "art"), name="art")

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(dist / "index.html")
