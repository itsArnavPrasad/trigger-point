"""Run receipts: what a pipeline run did, in which mode, at what cost, and what failed."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from trigger_point.models.context import Mode, RunMode

RunOutcome = Literal["running", "completed", "completed_with_gaps", "failed"]


class PageFailure(BaseModel):
    url: str
    status: str
    error: str | None


class LlmUsageRecord(BaseModel):
    task: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int | None
    request_id: str | None
    latency_ms: int
    # Token counts are reported by the provider; money cost is not computed here.


class RunReceipt(BaseModel):
    id: str
    kind: Literal["context_intake"]
    mode: RunMode
    initiated_by: str = "ui"
    provider_modes: dict[str, Mode] = Field(default_factory=dict)
    started_at: datetime
    finished_at: datetime | None = None
    outcome: RunOutcome = "running"
    seed_url: str
    context_id: str | None = None
    pages_attempted: int = 0
    pages_ok: int = 0
    page_failures: list[PageFailure] = Field(default_factory=list)
    unsupported_claim_count: int = 0
    llm_calls: list[LlmUsageRecord] = Field(default_factory=list)
    stage_ms: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
