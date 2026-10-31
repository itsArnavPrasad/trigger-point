"""Deterministic company identity resolution from /company/identify results.

Never picks "the first" of several equally confident matches: one exact domain can map to a
company page plus showcase pages (docs example: cashfree.com), and one name to several companies.
"""

from __future__ import annotations

from dataclasses import dataclass

from trigger_point.providers.crustdata.models import CompanyIdentifyData, IdentifyResult

MIN_CONFIDENCE = 0.9


@dataclass(frozen=True)
class Resolved:
    company_id: int
    company: CompanyIdentifyData
    reason: str


@dataclass(frozen=True)
class Ambiguous:
    candidates: list[CompanyIdentifyData]
    reason: str


@dataclass(frozen=True)
class NotFound:
    reason: str


Resolution = Resolved | Ambiguous | NotFound


def _is_showcase(c: CompanyIdentifyData) -> bool:
    url = (c.basic_info.professional_network_url if c.basic_info else None) or ""
    return "/showcase/" in url


def _owns_domain(c: CompanyIdentifyData, domain: str) -> bool:
    b = c.basic_info
    if b is None:
        return False
    return (b.primary_domain or "").lower() == domain or domain in [
        d.lower() for d in b.all_domains or []
    ]


def resolve_identity(result: IdentifyResult, queried_domain: str | None) -> Resolution:
    if not result.matches:
        return NotFound(f"no Crustdata match for {result.matched_on!r}")
    top = max(m.confidence_score for m in result.matches)
    best = [m.company_data for m in result.matches if m.confidence_score == top]
    if top < MIN_CONFIDENCE:
        return Ambiguous(best, f"best match confidence {top} is below {MIN_CONFIDENCE}")
    if len(best) == 1:
        return Resolved(best[0].crustdata_company_id, best[0], "single top-confidence match")
    narrowed = best
    notes: list[str] = []
    if queried_domain:
        domain = queried_domain.lower().removeprefix("www.")
        owning = [c for c in narrowed if _owns_domain(c, domain)]
        if owning and len(owning) < len(narrowed):
            notes.append(f"excluded {len(narrowed) - len(owning)} record(s) not owning {domain}")
            narrowed = owning
    pages = [c for c in narrowed if not _is_showcase(c)]
    if pages and len(pages) < len(narrowed):
        notes.append(f"excluded {len(narrowed) - len(pages)} showcase page(s)")
        narrowed = pages
    if len(narrowed) == 1:
        return Resolved(narrowed[0].crustdata_company_id, narrowed[0], "; ".join(notes))
    return Ambiguous(narrowed, f"{len(narrowed)} equally confident matches")
