"""JSON API for case files and outreach drafts. There is no send endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from trigger_point.api.routes_context import LOCAL_APPROVER
from trigger_point.cases.service import CaseNotFound, CaseService
from trigger_point.drafts.service import (
    DraftFailed,
    DraftNotAllowed,
    DraftNotFound,
    DraftService,
    DraftStateError,
)


class ApproveDraft(BaseModel):
    expected_hash: str = Field(min_length=64, max_length=64)


class EditDraft(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)


def cases_router(cases: CaseService, drafts: DraftService) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/research/{research_id}/accounts/{account_id}/case")
    def get_case(research_id: str, account_id: int) -> dict[str, Any]:
        try:
            return cases.get_or_build(research_id, account_id).model_dump(mode="json")
        except CaseNotFound as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.post("/research/{research_id}/accounts/{account_id}/drafts", status_code=201)
    def create_draft(research_id: str, account_id: int) -> dict[str, Any]:
        try:
            d = drafts.create(research_id, account_id)
        except CaseNotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except DraftNotAllowed as exc:
            raise HTTPException(409, {"error": "not_contactable", "message": str(exc)}) from exc
        except DraftFailed as exc:
            raise HTTPException(502, {"error": "draft_failed", "message": str(exc)}) from exc
        return {"draft_id": d.id, "status": d.status, "content_hash": d.content_hash}

    @router.get("/drafts/{draft_id}")
    def get_draft(draft_id: str) -> dict[str, Any]:
        try:
            return drafts.get(draft_id).model_dump(mode="json")
        except DraftNotFound as exc:
            raise HTTPException(404, "draft not found") from exc

    @router.patch("/drafts/{draft_id}")
    def edit_draft(draft_id: str, req: EditDraft) -> dict[str, Any]:
        try:
            d = drafts.edit(draft_id, req.subject, req.body)
        except DraftNotFound as exc:
            raise HTTPException(404, "draft not found") from exc
        return {"draft_id": d.id, "status": d.status, "content_hash": d.content_hash}

    @router.post("/drafts/{draft_id}/approve")
    def approve_draft(draft_id: str, req: ApproveDraft) -> dict[str, Any]:
        """Records approval of this exact content. Trigger Point never sends it."""
        try:
            d = drafts.approve(draft_id, req.expected_hash, LOCAL_APPROVER)
        except DraftNotFound as exc:
            raise HTTPException(404, "draft not found") from exc
        except DraftStateError as exc:
            raise HTTPException(409, {"error": "not_approvable", "message": str(exc)}) from exc
        return {
            "draft_id": d.id,
            "status": d.status,
            "approved_hash": d.approved_hash,
            "sending": d.sending,
        }

    return router
