"""Deterministic grounding: a fact counts as supported only if its quoted excerpt appears in the
stored text of the page it cites. This proves the quote exists, not that it entails the claim;
semantic adjudication belongs to the verifier stage.
"""

from __future__ import annotations

import html
import re
import unicodedata

from trigger_point.models.context import CLAIM_LIST_FIELDS, BusinessContext, ContextClaim

MIN_EXCERPT_CHARS = 12
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "})
_WS = re.compile(r"\s+")


def normalize_for_match(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES)
    return _WS.sub(" ", text).strip().casefold()


def _ground(claim: ContextClaim, field: str, pages: dict[str, str]) -> ContextClaim:
    def mark(status: str, reason: str | None = None) -> ContextClaim:
        return claim.model_copy(
            update={
                "status": status,
                "status_reason": reason,
                "verification_method": "exact_quote_match",
            }
        )

    if claim.kind == "user_provided":
        return claim.model_copy(update={"status": "not_applicable", "status_reason": None})
    if claim.kind == "inference":
        if field == "proof_points":
            return mark("unsupported", "proof_point_must_be_quoted_fact")
        return claim.model_copy(update={"status": "not_applicable", "status_reason": None})
    if claim.source_url not in pages:
        return mark("unsupported", "source_not_in_crawled_pages")
    if not claim.excerpt:
        return mark("unsupported", "missing_excerpt")
    excerpt = normalize_for_match(html.unescape(claim.excerpt))
    if len(excerpt) < MIN_EXCERPT_CHARS:
        return mark("unsupported", "excerpt_too_short")
    if excerpt not in normalize_for_match(pages[claim.source_url]):
        return mark("unsupported", "excerpt_not_found_in_source")
    return mark("supported")


def ground_context(ctx: BusinessContext, pages: dict[str, str]) -> BusinessContext:
    update: dict[str, object] = {
        name: [_ground(c, name, pages) for c in getattr(ctx, name)] for name in CLAIM_LIST_FIELDS
    }
    if ctx.company_name is not None:
        update["company_name"] = _ground(ctx.company_name, "company_name", pages)
    return ctx.model_copy(update=update)
