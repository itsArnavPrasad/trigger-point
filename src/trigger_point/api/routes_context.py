"""JSON API for business-context intake and review."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from trigger_point.context.service import (
    ContextNotFound,
    ContextService,
    IntakeFailed,
    InvalidEdit,
    UnsupportedFactsRemain,
    VersionMismatch,
)
from trigger_point.security.url_guard import UnsafeUrlError
from trigger_point.store.db import Store, VersionConflict

# No authentication in the MVP: approvals are attributed to a fixed local identity.
LOCAL_APPROVER = "local-user"


class IntakeRequest(BaseModel):
    website_url: str = Field(min_length=1, max_length=2048)
    goal: str = Field(min_length=1, max_length=4000)

    @field_validator("goal")
    @classmethod
    def _goal_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("goal must not be blank")
        return v


class EditRequest(BaseModel):
    set: dict[str, list[str]]


class ApproveRequest(BaseModel):
    acknowledge_unsupported: bool = False
    expected_version: int | None = None


CONCURRENT_WRITE = {"error": "concurrent_write", "message": "another change landed first; reload"}


def context_router(service: ContextService, store: Store) -> APIRouter:
    router = APIRouter(prefix="/api")

    def _get(context_id: str, version: int | None = None) -> dict[str, Any]:
        try:
            return {"id": context_id, **service.get(context_id, version).model_dump(mode="json")}
        except ContextNotFound as exc:
            raise HTTPException(404, "context not found") from exc

    @router.post("/contexts", status_code=201)
    def create_context(req: IntakeRequest) -> dict[str, Any]:
        try:
            out = service.intake(req.website_url, req.goal)
        except UnsafeUrlError as exc:
            raise HTTPException(422, {"error": "unsafe_url", "reason": exc.reason}) from exc
        except IntakeFailed as exc:
            raise HTTPException(
                502, {"error": "extraction_failed", "message": str(exc), "run_id": exc.run_id}
            ) from exc
        return {
            "context_id": out.context_id,
            "run_id": out.run_id,
            "version": out.context.version,
            "status": out.context.status,
        }

    @router.get("/contexts/{context_id}")
    def get_context(context_id: str, version: int | None = None) -> dict[str, Any]:
        return _get(context_id, version)

    @router.get("/contexts/{context_id}/versions")
    def list_versions(context_id: str) -> list[dict[str, Any]]:
        try:
            rows = service.versions(context_id)
        except ContextNotFound as exc:
            raise HTTPException(404, "context not found") from exc
        return [{"version": v, "status": s, "created_at": c} for v, s, c in rows]

    @router.patch("/contexts/{context_id}")
    def edit_context(context_id: str, req: EditRequest) -> dict[str, Any]:
        try:
            ctx = service.edit(context_id, req.set)
        except ContextNotFound as exc:
            raise HTTPException(404, "context not found") from exc
        except InvalidEdit as exc:
            raise HTTPException(422, str(exc)) from exc
        except VersionConflict as exc:
            raise HTTPException(409, CONCURRENT_WRITE) from exc
        return {"context_id": context_id, "version": ctx.version, "status": ctx.status}

    @router.post("/contexts/{context_id}/approve")
    def approve_context(context_id: str, req: ApproveRequest) -> dict[str, Any]:
        try:
            ctx = service.approve(
                context_id, LOCAL_APPROVER, req.acknowledge_unsupported, req.expected_version
            )
        except ContextNotFound as exc:
            raise HTTPException(404, "context not found") from exc
        except UnsupportedFactsRemain as exc:
            detail = {
                "error": "unsupported_facts",
                "unsupported": exc.texts,
                "hint": "edit them, or approve with acknowledge_unsupported=true to drop them",
            }
            raise HTTPException(409, detail) from exc
        except VersionMismatch as exc:
            raise HTTPException(
                409, {"error": "version_mismatch", "expected": exc.expected, "current": exc.current}
            ) from exc
        except VersionConflict as exc:
            raise HTTPException(409, CONCURRENT_WRITE) from exc
        return {"context_id": context_id, "version": ctx.version, "status": ctx.status}

    @router.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(404, "run not found")
        return run.model_dump(mode="json")

    return router
