"""Outreach to targets the user names, for each audience, from the approved profile only.

No provider is involved, so this works without Crustdata. The target is a user statement, the
audience sets the purpose and the ask, and code checks the result. Nothing here can send."""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass

from pydantic import BaseModel

from trigger_point.drafts.models import Finding
from trigger_point.drafts.verifier import (
    _EMAIL,
    _NUMBER,
    _PHONE,
    _PLACEHOLDER,
    BANNED_PHRASES,
    FAKE_FAMILIARITY,
)
from trigger_point.models.context import BusinessContext

PROMPT_VERSION = "outreach-prompt-v1"
OUTREACH_VERSION = "outreach-verifier-v1"
MAX_WORDS = 180
# Claims of existing use or results. The model reaches for these, and numbers cannot catch them.
_TRACTION = re.compile(
    r"\b(?:already|currently|are|now|have been)\s+(?:\w+\s+){0,2}"
    r"(?:running|piloting|working with|work with|partnered|serving|used by|trusted)"
    r"|\b(?:running|ran|completed)\s+(?:\w+\s+){0,3}pilots?\b"
    r"|\b(?:hundreds|thousands|many|several|dozens)\s+of\s+\w+"
    r"|\b(?:\w+\s+)?(?:schools|parents|students|families|customers)\s+"
    r"(?:\w+\s+){0,2}(?:trust|love|use|rely on|choose|recommend)\b",
    re.IGNORECASE,
)
# A first name introduced as the sender, or a sign-off. Words here are not names.
_SENDER = re.compile(
    r"\b(?:this is|my name is|i am|i'm)\s+([A-Z][a-z]+)\b"
    r"|(?:regards|sincerely|thanks|best|warmly),?\s*\n+\s*([A-Z][a-z]+)\b",
    re.IGNORECASE,
)
NOT_A_NAME = {"writing", "reaching", "from", "the", "team", "with", "one", "your", "a", "an"}
_CLAIM_NOUN = re.compile(
    r"\b(?:pilots?|schools?|parents?|students?|families|customers?|users?)\b", re.I
)
_RELATIVE_TIME = re.compile(r"\b(?:recently|last (?:week|month|year)|just (?:saw|read))\b", re.I)


@dataclass(frozen=True)
class Audience:
    label: str
    purpose: str
    ask: str


AUDIENCES: dict[str, Audience] = {
    "school_authority": Audience(
        "School authority",
        "Propose a small pilot with the school",
        "A short meeting to discuss a pilot",
    ),
    "parent": Audience(
        "Parent",
        "Explain what their child gets and invite them to talk",
        "A short conversation about their child",
    ),
    "company_buyer": Audience(
        "Company buyer",
        "Open a conversation about a problem they own",
        "A short call",
    ),
    "partner": Audience("Partner", "Explore working together", "A short introduction"),
}

SAMPLE_TARGETS: tuple[dict[str, str], ...] = (
    {"name": "SAMPLE CBSE school A, Mumbai", "audience": "school_authority", "notes": "Principal."},
    {"name": "SAMPLE CBSE school B, Mumbai", "audience": "school_authority", "notes": "Trustee."},
    {"name": "SAMPLE parent, Class 8 child", "audience": "parent", "notes": "Works in tech."},
    {"name": "SAMPLE parent, Class 10 child", "audience": "parent", "notes": "Board exam year."},
)

SYSTEM_PROMPT = f"""\
You write one short outreach message for a seller, using only the approved context given. A \
person reads it before anything happens, and code checks it.

Rules:
- Write to this audience, for this purpose, ending with this ask.
- State only what the approved context says. Never invent a result, a number, a customer, a \
partner, a pilot that has not happened, or anything about the recipient.
- Use a number only if it appears in the approved context or the user's notes.
- Never say you are running, have run or already have a pilot, customers, schools or users, \
unless the approved context says exactly that. Proposing a pilot is fine.
- Sign as the company. Never give a sender's name unless the approved context names them.
- Do not pretend to know the recipient. Do not say you noticed, saw or admired anything.
- Do not use placeholders such as [Name]. Write so that no name is needed.
- Under {MAX_WORDS} words. Plain and respectful. No hype.
- claims: each factual statement you made, copied from the message.
"""


class OutreachClaim(BaseModel):
    text: str
    kind: str


class OutreachWire(BaseModel):
    subject: str
    body: str
    claims: list[OutreachClaim]


def content_hash(target_id: str, subject: str, body: str) -> str:
    return hashlib.sha256(f"{target_id}\n{subject}\n{body}".encode()).hexdigest()


def approved_facts(ctx: BusinessContext) -> list[str]:
    return [c.text for _, c in ctx.iter_claims() if c.status != "unsupported"]


def _numbers(text: str) -> set[str]:
    """ "10," and "10" are the same number."""
    return {n.rstrip(",") for n in _NUMBER.findall(text)}


def _sentence(text: str, start: int, end: int) -> str:
    left = max(text.rfind(c, 0, start) for c in ".!?\n") + 1
    rights = [i for i in (text.find(c, end) for c in ".!?\n") if i >= 0]
    return text[left : min(rights, default=len(text))]


def _backed(sentence: str, facts: list[str]) -> bool:
    """A claim of use is backed when one approved fact names everything the sentence names."""
    named = {w.casefold() for w in _CLAIM_NOUN.findall(sentence)}
    if not named:
        return False
    return any(all(w in fact.casefold() for w in named) for fact in facts)


def verify_outreach(
    wire: OutreachWire, facts: list[str], target_name: str, notes: str = ""
) -> list[Finding]:
    copy = f"{wire.subject}\n{wire.body}"
    low = copy.casefold()
    known = " ".join([*facts, notes, target_name])
    allowed = _numbers(known)
    findings: list[Finding] = []

    def err(code: str, message: str) -> None:
        findings.append(Finding(code=code, severity="error", message=message))

    for number in sorted(_numbers(copy) - allowed):
        err("unsupported_number", f"{number} is not in the approved context or your notes")
    for m in _TRACTION.finditer(copy):
        if not _backed(_sentence(copy, m.start(), m.end()), facts):
            err("unsupported_traction", f"Claims use or results with no approved fact: {m[0]}")
    for m in _SENDER.finditer(wire.body):
        name = m[1] or m[2]
        if name.casefold() not in NOT_A_NAME and name.casefold() not in known.casefold():
            err("invented_person", f"{name} is not in the approved context or your notes")
    for phrase in FAKE_FAMILIARITY:
        if phrase in low:
            err("fake_familiarity", f"Pretends to know the recipient: {phrase}")
    for phrase in BANNED_PHRASES:
        if phrase in low:
            err("banned_phrase", f"Banned phrase: {phrase}")
    if _EMAIL.search(copy) or _PHONE.search(copy):
        err("contact_data", "Contact details do not belong in the draft")
    if _PLACEHOLDER.search(copy):
        err("placeholder", "Contains an unfilled placeholder")
    if _RELATIVE_TIME.search(copy):
        err("relative_time", "Claims something happened recently")
    if len(wire.body.split()) > MAX_WORDS:
        err("too_long", f"Over {MAX_WORDS} words")
    if not wire.subject.strip() or not wire.body.strip():
        err("empty", "Subject or body is empty")
    return findings


def build_outreach_message(
    ctx: BusinessContext, audience: Audience, target_name: str, notes: str
) -> str:
    facts = "\n".join(f"- {html.escape(f, quote=False)}" for f in approved_facts(ctx))
    return (
        f"Seller: {html.escape(ctx.company_name.text if ctx.company_name else ctx.domain)}\n"
        f"Audience: {audience.label}\nPurpose: {audience.purpose}\nAsk: {audience.ask}\n"
        f"<recipient>{html.escape(target_name, quote=False)}</recipient>\n"
        f"<user_notes>{html.escape(notes, quote=False)}</user_notes>\n"
        f"<approved_context>\n{facts}\n</approved_context>"
    )
