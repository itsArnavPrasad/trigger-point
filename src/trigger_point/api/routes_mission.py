"""JSON API for missions and discovery runs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from trigger_point.context.service import ContextNotFound
from trigger_point.mission.service import (
    ContextNotApproved,
    DiscoveryFailed,
    DiscoveryService,
    MissionCompileFailed,
    MissionNotApproved,
    MissionNotFound,
    MissionService,
)
from trigger_point.research.service import ResearchFailed, ResearchNotFound, ResearchService


def mission_router(
    missions: MissionService, discovery: DiscoveryService, research: ResearchService
) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.post("/contexts/{context_id}/missions", status_code=201)
    def create_mission(context_id: str) -> dict[str, Any]:
        try:
            m = missions.compile(context_id)
        except ContextNotFound as exc:
            raise HTTPException(404, "context not found") from exc
        except ContextNotApproved as exc:
            raise HTTPException(
                409, {"error": "context_not_approved", "message": str(exc)}
            ) from exc
        except MissionCompileFailed as exc:
            raise HTTPException(
                502, {"error": "mission_compile_failed", "message": str(exc)}
            ) from exc
        return {"mission_id": m.id, "status": m.status, "estimated_credits": m.estimated_credits}

    @router.get("/missions/{mission_id}")
    def get_mission(mission_id: str) -> dict[str, Any]:
        try:
            return missions.get(mission_id).model_dump(mode="json")
        except MissionNotFound as exc:
            raise HTTPException(404, "mission not found") from exc

    @router.post("/missions/{mission_id}/approve")
    def approve_mission(mission_id: str) -> dict[str, Any]:
        try:
            m = missions.approve(mission_id)
        except MissionNotFound as exc:
            raise HTTPException(404, "mission not found") from exc
        return {"mission_id": m.id, "status": m.status}

    @router.post("/missions/{mission_id}/discover", status_code=201)
    def discover(mission_id: str) -> dict[str, Any]:
        try:
            run = discovery.run(mission_id)
        except MissionNotFound as exc:
            raise HTTPException(404, "mission not found") from exc
        except MissionNotApproved as exc:
            raise HTTPException(409, {"error": "mission_not_approved"}) from exc
        except DiscoveryFailed as exc:
            raise HTTPException(
                502,
                {
                    "error": "discovery_failed",
                    "message": str(exc),
                    "discovery_id": exc.discovery_id,
                },
            ) from exc
        return {"discovery_id": run.id, "outcome": run.outcome, "accounts": len(run.accounts)}

    @router.get("/discoveries/{discovery_id}")
    def get_discovery(discovery_id: str) -> dict[str, Any]:
        run = discovery.get(discovery_id)
        if run is None:
            raise HTTPException(404, "discovery not found")
        return run.model_dump(mode="json")

    @router.post("/discoveries/{discovery_id}/research", status_code=201)
    def run_research(discovery_id: str) -> dict[str, Any]:
        try:
            run = research.run(discovery_id)
        except ResearchNotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except ResearchFailed as exc:
            raise HTTPException(
                502,
                {"error": "research_failed", "message": str(exc), "research_id": exc.research_id},
            ) from exc
        return {"research_id": run.id, "outcome": run.outcome, "accounts": len(run.accounts)}

    @router.get("/research/{research_id}")
    def get_research(research_id: str) -> dict[str, Any]:
        try:
            return research.get(research_id).model_dump(mode="json")
        except ResearchNotFound as exc:
            raise HTTPException(404, "research run not found") from exc

    return router
