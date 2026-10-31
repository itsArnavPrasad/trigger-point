"""Deterministic case-file assembly. No LLM: every sentence is derived from evidence or is a
templated, explicitly labelled hypothesis."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from trigger_point.cases.models import AccountCase, CaseItem, Route
from trigger_point.mission.models import GTMPlan
from trigger_point.models.context import BusinessContext, Mode
from trigger_point.models.evidence import Evidence, evidence_id
from trigger_point.research.service import AccountResearch

SELLER_PROOF_FIELDS = ("proof_points", "value_propositions", "differentiators")
MAX_SELLER_ITEMS = 4
WARM_PATH_NONE = (
    "No relationship evidence is connected (no shared-employer, school or network "
    "data), so a warm introduction is not available."
)


def _provided_at(ctx: BusinessContext) -> datetime:
    """User-provided facts enter the record when the user approves the context."""
    if ctx.approved_at is not None:
        return ctx.approved_at
    if ctx.pages:
        return ctx.pages[0].retrieved_at
    raise ValueError("seller evidence requires an approved context")


def seller_evidence(ctx: BusinessContext, context_id: str) -> list[Evidence]:
    """Only approved, quote-verified facts and the seller's own edits can support 'why us'."""
    out: list[Evidence] = []
    pages = {p.url: p for p in ctx.pages}
    for field in SELLER_PROOF_FIELDS:
        for c in getattr(ctx, field):
            if c.kind == "fact" and c.status == "supported":
                page = pages.get(c.source_url or "")
                out.append(
                    Evidence(
                        id=evidence_id("seller", ctx.domain, field, c.text, c.source_url),
                        entity_type="seller",
                        entity_id=context_id,
                        claim=c.text,
                        source_kind="seller_website",
                        source_url=c.source_url,
                        publisher=ctx.domain,
                        retrieved_at=page.retrieved_at if page else _provided_at(ctx),
                        excerpt=c.excerpt,
                    )
                )
            elif c.kind == "user_provided":
                out.append(
                    Evidence(
                        id=evidence_id("seller", ctx.domain, field, c.text, c.source_url),
                        entity_type="seller",
                        entity_id=context_id,
                        claim=c.text,
                        source_kind="user_provided",
                        publisher="seller (approved by user)",
                        retrieved_at=_provided_at(ctx),
                        excerpt=None,
                    )
                )
    return out


def _profile_evidence(ar: AccountResearch) -> Evidence | None:
    c = ar.account
    parts = []
    if c.employee_count_range:
        parts.append(f"{c.employee_count_range} employees")
    if c.headcount_total is not None:
        parts.append(f"headcount {c.headcount_total}")
    if c.hq_country:
        parts.append(f"located in {c.hq_country}")
    if not parts:
        return None
    as_of = date.fromisoformat(c.provider_updated_at[:10]) if c.provider_updated_at else None
    return Evidence(
        id=evidence_id("profile", c.provider_company_id, *parts),
        entity_type="account",
        entity_id=str(c.provider_company_id),
        claim=f"{c.name or 'The company'} ({c.primary_domain}): {', '.join(parts)} "
        f"(Crustdata{', as of ' + as_of.isoformat() if as_of else ''}).",
        source_kind="provider_field",
        publisher="Crustdata",
        as_of=as_of,
        provider_ref="crustdata:/company/search:basic_info,headcount,locations",
        retrieved_at=c.retrieved_at,
    )


def _route(ar: AccountResearch, hooks: list[str]) -> tuple[Route, str, str]:
    s = ar.score
    name = ar.best_person.person.name if ar.best_person else None
    if s.status == "rejected":
        return (
            "do_not_contact",
            f"rejected: {', '.join(s.rejections)}",
            "Do not contact. Recheck when new signals appear.",
        )
    if s.status == "insufficient_evidence" or ar.best_person is None or not hooks:
        missing = [k for k, c in s.components.items() if not c.known]
        reason = "insufficient evidence" + (f" (unknown: {', '.join(missing)})" if missing else "")
        if ar.best_person is None:
            reason += "; no verified buyer yet"
        return (
            "research_more",
            reason,
            "Research further (find a verified buyer or a fresh signal) before any outreach.",
        )
    return (
        "cold_email",
        f"qualified (tier {s.tier}), verified buyer, {len(hooks)} active hook(s); no warm "
        "path evidence, so a contextual cold email",
        f"Draft a first-touch email to {name} and review it before any action.",
    )


def build_case(
    ar: AccountResearch,
    plan: GTMPlan,
    ctx: BusinessContext,
    context_id: str,
    research_id: str,
    reference_date: date,
    now: datetime,
    mode: Mode,
) -> AccountCase:
    c = ar.account
    name = c.name or c.primary_domain or str(c.provider_company_id)
    seller = ctx.company_name.text if ctx.company_name else ctx.domain
    evidence = list(ar.evidence)
    by_id = {e.id: e for e in evidence}

    why_account: list[CaseItem] = []
    profile = _profile_evidence(ar)
    if profile:
        evidence.append(profile)
        fit = ar.score.components["fit"]
        why_account.append(CaseItem(text=profile.claim, kind="fact", evidence_ids=[profile.id]))
        if fit.known:
            why_account.append(
                CaseItem(
                    text=f"Against the mission criteria: {fit.detail}.",
                    kind="fact",
                    evidence_ids=[profile.id],
                )
            )
    for eid in ar.tech_evidence_ids:
        why_account.append(CaseItem(text=by_id[eid].claim, kind="fact", evidence_ids=[eid]))
    if not why_account:
        why_account.append(CaseItem(text="Firmographics unknown in Crustdata.", kind="unknown"))

    why_person: list[CaseItem] = []
    if ar.best_person:
        m = ar.best_person
        person_ev = [
            e
            for e in evidence
            if e.entity_type == "person" and e.entity_id == str(m.person.provider_person_id)
        ]
        why_person.append(
            CaseItem(
                text=person_ev[0].claim if person_ev else m.person.name or "",
                kind="fact",
                evidence_ids=[e.id for e in person_ev],
            )
        )
        why_person.append(
            CaseItem(
                text=f"Persona {m.persona_title}: {m.persona_why} (match: {m.reason}).",
                kind="inference",
            )
        )
    elif ar.people_searched:
        why_person.append(
            CaseItem(
                text="No verified buyer at this account: "
                + (
                    ", ".join(sorted({r.reason for r in ar.people_rejected}))
                    or "no matching profiles"
                ),
                kind="unknown",
            )
        )
    else:
        why_person.append(
            CaseItem(
                text="People not searched yet (outside the top accounts or budget).", kind="unknown"
            )
        )

    active = [s for s in ar.signals if s.status == "active"]
    hooks = sorted({eid for s in active for eid in s.evidence_ids})
    why_now = [
        CaseItem(text=s.description, kind="fact", evidence_ids=s.evidence_ids) for s in active
    ]
    if not why_now:
        why_now.append(CaseItem(text="No fresh, dated reason to act now.", kind="unknown"))

    sellers = seller_evidence(ctx, context_id)[:MAX_SELLER_ITEMS]
    evidence.extend(sellers)
    why_us = [CaseItem(text=e.claim, kind="fact", evidence_ids=[e.id]) for e in sellers]
    if active:
        kinds = ", ".join(sorted({s.type.replace("_", " ") for s in active}))
        why_us.append(
            CaseItem(
                text=f"Hypothesis: {seller} may be relevant to {name} because of {kinds}. "
                "This is an inference, not evidence of budget, pain or intent.",
                kind="inference",
                evidence_ids=hooks + [e.id for e in sellers],
            )
        )
    if not why_us:
        why_us.append(CaseItem(text="No approved seller proof points.", kind="unknown"))

    hypotheses = [
        CaseItem(text=p.text, kind="inference") for p in ctx.customer_pains if p.kind != "fact"
    ]
    gaps = [f"{k}: {comp.detail}" for k, comp in ar.score.components.items() if not comp.known]
    gaps += [
        f"{s.status} signal not used as a hook: {s.description}"
        for s in ar.signals
        if s.status != "active"
    ]
    if "recent_funding" in plan.signal_types:
        gaps.append("recent_funding not collected in this run")

    expiries: list[date] = []
    for s in active:
        reference = s.event_on or s.as_of
        if reference is not None:
            expiries.append(reference + timedelta(days=s.window_days))
    route, reason, action = _route(ar, hooks)
    return AccountCase(
        id=evidence_id("case", research_id, c.provider_company_id),
        research_id=research_id,
        context_id=context_id,
        account_id=c.provider_company_id,
        account_name=c.name,
        account_domain=c.primary_domain,
        seller_name=seller,
        mode=mode,
        created_at=now,
        reference_date=reference_date,
        why_account=why_account,
        why_person=why_person,
        why_now=why_now,
        why_us=why_us,
        hypotheses=hypotheses,
        coverage_gaps=gaps,
        warm_path=WARM_PATH_NONE,
        recommended_route=route,
        route_reason=reason,
        next_best_action=action,
        score=ar.score,
        recipient=ar.best_person if route == "cold_email" else None,
        hook_evidence_ids=hooks if route == "cold_email" else [],
        seller_evidence_ids=[e.id for e in sellers],
        expires_on=min(expiries) if expiries else None,
        evidence=evidence,
    )
