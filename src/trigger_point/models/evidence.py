"""Evidence registry: every fact shown about an account, person or seller is one entry."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

EntityType = Literal["account", "person", "seller"]
SourceKind = Literal[
    "provider_field",
    "job_posting",
    "social_post",
    "provider_profile",
    "seller_website",
    "user_provided",
]


class Evidence(BaseModel):
    """`event_on` is when something happened (e.g. a job was posted); `as_of` is when a metric
    was measured or a record refreshed by the provider; `retrieved_at` is when Trigger Point fetched it.
    They are never substituted for one another."""

    model_config = ConfigDict(frozen=True)

    id: str
    entity_type: EntityType
    entity_id: str
    claim: str
    source_kind: SourceKind
    source_url: str | None = None
    provider_ref: str | None = None
    publisher: str | None = None
    event_on: date | None = None
    as_of: date | None = None
    retrieved_at: datetime
    excerpt: str | None = None
    confidence: Literal["high", "medium", "low"] = "high"


def evidence_id(*parts: object) -> str:
    raw = json.dumps([str(p) for p in parts], separators=(",", ":"))
    return "ev_" + hashlib.sha256(raw.encode()).hexdigest()[:12]
