"""Deterministic draft verifier (verifier-v1). Errors block approval; warnings are shown.

Rules come from docs/OUTREACH_POLICY.md and docs/EVIDENCE_AND_VERIFICATION.md: every fact cites
case evidence, the hook is an active signal, any proof point is approved seller evidence, every
number appears in cited evidence, no fabricated familiarity, no other prospect, no contact data,
one concise message.
"""

from __future__ import annotations

import re

from trigger_point.cases.models import AccountCase
from trigger_point.drafts.models import DraftWire, Finding

VERIFIER_VERSION = "verifier-v1"
MAX_WORDS = 120
BANNED_PHRASES = (
    "hope this finds you well",
    "hope you're well",
    "quick question",
    "just checking in",
    "touch base",
    "circle back",
    "leverage",
    "delve",
    "streamline",
    "game-changer",
    "game changer",
    "revolutionize",
    "synergy",
    "world-class",
    "best-in-class",
    "i noticed",
    "i came across your profile",
)
FAKE_FAMILIARITY = (
    "mutual connection",
    "mutual friend",
    "we met",
    "as we discussed",
    "as discussed",
    "following up on our conversation",
    "great chatting",
    "per our conversation",
    "you mentioned",
    "reaching out again",
)
_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?%?")
_MEETING_LENGTH = re.compile(r"\b\d+\s*-?\s*(?:minute|min)s?\b", re.IGNORECASE)
_PLACEHOLDER = re.compile(r"\{[^}]*\}|<<[^>]*>>|\[(?!your name\])[^\]]+\]", re.IGNORECASE)
# Past-relative time drifts from the evidence date; the copy must use the date itself.
_RELATIVE_PAST = re.compile(
    r"\b(?:last (?:week|month|year|quarter)|yesterday|earlier this (?:week|month|year)|"
    r"(?:\d+|a few|a couple of|several) (?:days?|weeks?|months?) ago)\b",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?:\+\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")


def _err(code: str, message: str) -> Finding:
    return Finding(code=code, severity="error", message=message)


def _warn(code: str, message: str) -> Finding:
    return Finding(code=code, severity="warning", message=message)


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUMBER.findall(_MEETING_LENGTH.sub(" ", text))}


def _mentions(text: str, name: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.IGNORECASE) is not None


def verify_draft(
    draft: DraftWire, case: AccountCase, other_account_names: list[str]
) -> list[Finding]:
    findings: list[Finding] = []
    copy = f"{draft.subject}\n{draft.body}"
    lowered = copy.casefold()
    evidence = {e.id: e for e in case.evidence}

    if case.recommended_route != "cold_email" or case.recipient is None:
        findings.append(
            _err("not_contactable", f"case route is {case.recommended_route}: {case.route_reason}")
        )
    if draft.hook_evidence_id not in case.hook_evidence_ids:
        findings.append(
            _err("invalid_hook", "the hook must be one of the case's active why-now signals")
        )
    if (
        draft.proof_point_evidence_id
        and draft.proof_point_evidence_id not in case.seller_evidence_ids
    ):
        findings.append(
            _err("invalid_proof_point", "proof points must come from the approved seller context")
        )

    cited: set[str] = {draft.hook_evidence_id}
    if draft.proof_point_evidence_id:
        cited.add(draft.proof_point_evidence_id)
    for claim in draft.claims:
        unknown = [eid for eid in claim.evidence_ids if eid not in evidence]
        if unknown:
            findings.append(
                _err("unknown_evidence", f"claim {claim.text!r} cites unknown evidence {unknown}")
            )
        if claim.kind == "fact" and not claim.evidence_ids:
            findings.append(_err("uncited_fact", f"fact {claim.text!r} has no evidence"))
        cited.update(eid for eid in claim.evidence_ids if eid in evidence)
    for step in draft.follow_ups:
        unknown = [eid for eid in step.evidence_ids if eid not in evidence]
        if unknown:
            findings.append(
                _err(
                    "unknown_evidence", f"follow-up {step.angle!r} cites unknown evidence {unknown}"
                )
            )

    allowed = set().union(
        *(
            _numbers(f"{evidence[e].claim} {evidence[e].excerpt or ''}")
            for e in cited
            if e in evidence
        )
    )
    invented = sorted(_numbers(copy) - allowed)
    if invented:
        findings.append(
            _err(
                "unsupported_number", f"numbers not found in cited evidence: {', '.join(invented)}"
            )
        )

    for phrase in BANNED_PHRASES:
        if phrase in lowered:
            findings.append(_err("banned_phrase", f"remove {phrase!r}"))
    for phrase in FAKE_FAMILIARITY:
        if phrase in lowered:
            findings.append(
                _err("fake_familiarity", f"{phrase!r} implies a relationship that is not evidenced")
            )
    for other in other_account_names:
        if other and other != case.account_name and _mentions(copy, other):
            findings.append(_err("wrong_entity", f"mentions another prospect: {other}"))
    if case.account_name and not _mentions(copy, case.account_name):
        findings.append(_warn("missing_account_name", "the account is not named"))

    words = len(draft.body.split())
    if words > MAX_WORDS:
        findings.append(_err("too_long", f"{words} words; limit is {MAX_WORDS}"))
    for ph in _PLACEHOLDER.findall(copy):
        findings.append(_err("placeholder", f"unfilled placeholder {ph}"))
    if _EMAIL.search(copy) or _PHONE.search(copy):
        findings.append(_err("private_data", "contact details must not appear in the copy"))

    for m in _RELATIVE_PAST.finditer(copy):
        findings.append(
            _err(
                "relative_time", f"{m.group(0)!r}: state the evidence date instead of relative time"
            )
        )
    hook = evidence.get(draft.hook_evidence_id)
    if hook is not None:
        cues = [hook.excerpt or ""] + sorted(_numbers(hook.claim) - {"2026", "2025"})
        if not any(c and c.casefold() in lowered for c in cues):
            findings.append(_warn("hook_not_used", "the chosen hook is not visible in the copy"))

    asks = copy.count("?")
    if asks == 0:
        findings.append(_warn("missing_ask", "no clear question or ask"))
    elif asks > 2:
        findings.append(_warn("too_many_asks", f"{asks} questions; keep one ask"))
    if "—" in copy:
        findings.append(_warn("em_dash", "em dashes read as generated copy"))
    return findings


def passes(findings: list[Finding]) -> bool:
    return not any(f.severity == "error" for f in findings)
