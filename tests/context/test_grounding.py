import pytest
from pydantic import ValidationError

from tests.context.factories import PAGES, PRICING, context, fact, inference
from trigger_point.context.grounding import ground_context
from trigger_point.models.context import ContextClaim, ContextDraft


def test_fact_with_present_excerpt_is_supported_case_and_space_insensitive() -> None:
    ctx = context(
        value_propositions=[fact("Automates tickets", excerpt="RESOLVES 60%  of support   tickets")]
    )
    grounded = ground_context(ctx, PAGES)
    claim = grounded.value_propositions[0]
    assert claim.status == "supported"
    assert claim.verification_method == "exact_quote_match"


def test_fact_with_absent_excerpt_is_unsupported() -> None:
    ctx = context(proof_points=[fact("Resolves 90% of tickets", excerpt="resolves 90% of tickets")])
    claim = ground_context(ctx, PAGES).proof_points[0]
    assert claim.status == "unsupported"
    assert claim.status_reason == "excerpt_not_found_in_source"


def test_fact_citing_uncrawled_url_is_unsupported() -> None:
    ctx = context(use_cases=[fact("x", url="https://acme.com/secret", excerpt="Plans start at")])
    claim = ground_context(ctx, PAGES).use_cases[0]
    assert claim.status == "unsupported"
    assert claim.status_reason == "source_not_in_crawled_pages"


def test_fact_without_excerpt_is_unsupported() -> None:
    claim = ground_context(context(use_cases=[fact("x", excerpt=None)]), PAGES).use_cases[0]
    assert claim.status == "unsupported"
    assert claim.status_reason == "missing_excerpt"


def test_trivially_short_excerpt_is_unsupported() -> None:
    claim = ground_context(context(use_cases=[fact("x", excerpt="Acme")]), PAGES).use_cases[0]
    assert claim.status == "unsupported"
    assert claim.status_reason == "excerpt_too_short"


def test_inference_is_not_applicable() -> None:
    claim = ground_context(
        context(customer_pains=[inference("Support teams are overloaded")]), PAGES
    ).customer_pains[0]
    assert claim.status == "not_applicable"


def test_proof_point_cannot_be_an_inference() -> None:
    claim = ground_context(
        context(proof_points=[inference("Trusted by Fortune 500")]), PAGES
    ).proof_points[0]
    assert claim.status == "unsupported"
    assert claim.status_reason == "proof_point_must_be_quoted_fact"


def test_company_name_is_grounded_too() -> None:
    ctx = context()
    ctx = ctx.model_copy(update={"company_name": fact("Acme", excerpt="Acme resolves 60%")})
    assert ground_context(ctx, {PRICING: PAGES[PRICING]}).company_name is not None
    grounded = ground_context(ctx, {PRICING: PAGES[PRICING]})
    assert grounded.company_name is not None and grounded.company_name.status == "unsupported"


def test_grounding_is_pure() -> None:
    ctx = context(use_cases=[fact("x", excerpt="Plans start at $99", url=PRICING)])
    ground_context(ctx, PAGES)
    assert ctx.use_cases[0].status == "pending"


def test_at_most_three_clarification_questions() -> None:
    with pytest.raises(ValidationError):
        ContextDraft(clarification_questions=["a?", "b?", "c?", "d?"])


def test_fact_requires_source_url() -> None:
    with pytest.raises(ValidationError):
        ContextClaim(text="x", kind="fact", confidence="high")


def test_unsupported_claims_listing() -> None:
    ctx = ground_context(
        context(use_cases=[fact("x", excerpt=None)], value_propositions=[inference("y")]), PAGES
    )
    assert [c.text for c in ctx.unsupported_claims()] == ["x"]
