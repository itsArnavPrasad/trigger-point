from datetime import date

from tests.context.factories import context, fact, inference
from tests.research.factories import NOW, TODAY, company, person, plan, posting
from trigger_point.cases.builder import build_case, seller_evidence
from trigger_point.context.grounding import ground_context
from trigger_point.research.people import match_people
from trigger_point.research.scoring import PeopleOutcome, score_account
from trigger_point.research.service import AccountResearch
from trigger_point.research.signals import signals_from_company, signals_from_postings

PAGES = {
    "https://acme.com/": "Acme resolves up to 45% of inbound tickets for SaaS teams. "
    "Integrates natively with Zendesk."
}


def approved_context():  # type: ignore[no-untyped-def]
    ctx = context(
        value_propositions=[
            fact("Native Zendesk integration", excerpt="Integrates natively with Zendesk")
        ],
        proof_points=[
            fact(
                "Resolves up to 45% of inbound tickets",
                excerpt="resolves up to 45% of inbound tickets",
            ),
            fact("Invented proof", excerpt="this text is not on the page"),
        ],
        customer_pains=[inference("Support teams are overloaded")],
    )
    return ground_context(ctx, PAGES).model_copy(update={"status": "approved"})


def research(people=True, postings=True, **company_over):  # type: ignore[no-untyped-def]
    c = company(**company_over)
    p = plan()
    sigs, evs = signals_from_company(c, p, TODAY)
    ps = signals_from_postings([posting()] if postings else [], p, TODAY)
    sigs += ps.signals.get(1001, [])
    evs += [e for e in ps.evidence if e.entity_id == "1001"]
    matches = match_people([person()], 1001, p) if people else None
    best = matches.best if matches else None
    score = score_account(
        c,
        sigs,
        len(ps.tech_evidence.get(1001, [])),
        PeopleOutcome(searched=people, best_match_confidence=best.confidence if best else None),
        p,
        signals_collected=True,
    )
    if best:
        from trigger_point.research.service import _person_evidence

        evs.append(_person_evidence(best, c))
    return AccountResearch(
        account=c,
        signals=sigs,
        evidence=evs,
        tech_evidence_ids=[e.id for e in ps.tech_evidence.get(1001, [])],
        people_searched=people,
        best_person=best,
        score=score,
    ), p


def test_seller_evidence_uses_only_approved_supported_facts() -> None:
    evs = seller_evidence(approved_context(), "ctx1")
    claims = [e.claim for e in evs]
    assert "Resolves up to 45% of inbound tickets" in claims
    assert "Invented proof" not in claims  # unsupported quote
    assert "Support teams are overloaded" not in claims  # inference is never proof
    assert all(e.entity_type == "seller" and e.source_url for e in evs)


def test_qualified_account_case_answers_four_whys_with_cited_facts() -> None:
    ar, p = research()
    case = build_case(
        ar,
        p,
        approved_context(),
        "ctx1",
        research_id="r1",
        reference_date=TODAY,
        now=NOW,
        mode="replay",
    )
    assert case.recommended_route == "cold_email"
    ids = {e.id for e in case.evidence}
    for section in (case.why_account, case.why_person, case.why_now, case.why_us):
        assert section, "every why must be answered"
        for item in section:
            if item.kind == "fact":
                assert item.evidence_ids and set(item.evidence_ids) <= ids
    assert any(i.kind == "inference" for i in case.why_us)  # relevance is a hypothesis
    assert any(i.kind == "inference" for i in case.why_person)  # persona why
    assert case.hook_evidence_ids and set(case.hook_evidence_ids) <= ids
    assert case.recipient is not None and case.recipient.person.name == "Ana Example"
    assert "No relationship evidence" in case.warm_path


def test_expiry_is_the_earliest_hook_expiry() -> None:
    ar, p = research()
    case = build_case(ar, p, approved_context(), "ctx1", "r1", TODAY, NOW, "replay")
    # posting 2026-10-15 + 30 days; metrics as of 2026-10-21 + 180 days
    assert case.expires_on == date(2026, 11, 14)


def test_rejected_account_is_do_not_contact_with_reason() -> None:
    ar, p = research(people=True, postings=False, headcount_growth_6m_pct=1.0, hiring_openings=0)
    case = build_case(ar, p, approved_context(), "ctx1", "r1", TODAY, NOW, "replay")
    assert case.recommended_route == "do_not_contact"
    assert "no_fresh_why_now" in case.route_reason
    assert case.hook_evidence_ids == []


def test_unsearched_people_means_research_more_not_contact() -> None:
    ar, p = research(people=False)
    case = build_case(ar, p, approved_context(), "ctx1", "r1", TODAY, NOW, "replay")
    assert case.recommended_route == "research_more"
    assert any(i.kind == "unknown" for i in case.why_person)


def test_expired_signals_are_listed_as_gaps_not_hooks() -> None:
    ar, p = research(provider_updated_at="2026-03-04T00:00:00Z")
    case = build_case(ar, p, approved_context(), "ctx1", "r1", TODAY, NOW, "replay")
    assert any("expired" in g for g in case.coverage_gaps)
    hook_signals = [s for s in ar.signals if set(s.evidence_ids) & set(case.hook_evidence_ids)]
    assert all(s.status == "active" for s in hook_signals)


def test_seller_evidence_ids_are_content_based_not_run_based() -> None:
    a = [e.id for e in seller_evidence(approved_context(), "context-run-1")]
    b = [e.id for e in seller_evidence(approved_context(), "context-run-2")]
    assert a == b
