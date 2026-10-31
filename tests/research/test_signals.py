from datetime import date

from tests.research.factories import TODAY, company, plan, posting
from trigger_point.research.signals import (
    signals_from_company,
    signals_from_postings,
    wants_postings,
)


def by_type(signals: list) -> dict:  # type: ignore[type-arg]
    return {s.type: s for s in signals}


def test_growth_metric_is_as_of_provider_refresh_not_an_event() -> None:
    sigs, evidence = signals_from_company(company(), plan(), TODAY)
    growth = by_type(sigs)["headcount_growth"]
    assert growth.event_on is None
    assert growth.as_of == date(2026, 10, 21)
    assert growth.age_days == 10 and growth.status == "active"
    assert growth.strength == 0.7
    [ev] = [e for e in evidence if e.id in growth.evidence_ids]
    assert "14.2%" in ev.claim and "as of 2026-10-21" in ev.claim
    assert ev.provider_ref == "crustdata:/company/search:headcount.growth_percent.6m"


def test_small_growth_creates_no_signal() -> None:
    sigs, _ = signals_from_company(
        company(headcount_growth_6m_pct=3.0, hiring_openings=1), plan(), TODAY
    )
    assert sigs == []


def test_stale_provider_record_expires_metric_signals() -> None:
    sigs, _ = signals_from_company(
        company(provider_updated_at="2026-03-04T00:00:00Z"), plan(), TODAY
    )
    assert by_type(sigs)["headcount_growth"].status == "expired"
    assert by_type(sigs)["active_hiring"].status == "expired"


def test_missing_provider_date_is_undated_never_retrieval_time() -> None:
    sigs, _ = signals_from_company(company(provider_updated_at=None), plan(), TODAY)
    s = by_type(sigs)["headcount_growth"]
    assert s.status == "undated" and s.as_of is None and s.age_days is None


def test_openings_count_strength_table() -> None:
    sigs, _ = signals_from_company(company(hiring_openings=12), plan(), TODAY)
    assert by_type(sigs)["active_hiring"].strength == 0.6


def test_signal_types_not_in_plan_are_not_collected() -> None:
    sigs, _ = signals_from_company(company(), plan(signal_types=["support_team_growth"]), TODAY)
    assert sigs == []


def test_function_job_posting_is_dated_fresh_and_cited() -> None:
    result = signals_from_postings([posting()], plan(), TODAY)
    [sig] = result.signals[1001]
    assert sig.type == "support_team_growth" and sig.status == "active"
    assert sig.event_on == date(2026, 10, 15) and sig.age_days == 16
    [ev] = [e for e in result.evidence if e.id in sig.evidence_ids]
    assert ev.source_url == "https://jobs.example/9001" and ev.event_on == date(2026, 10, 15)
    assert "posted 2026-10-15" in ev.claim and "last seen 2026-10-28" in ev.claim


def test_old_and_undated_postings_never_count_as_fresh() -> None:
    result = signals_from_postings(
        [posting(9002, posted_on=date(2026, 9, 4)), posting(9003, posted_on=None)], plan(), TODAY
    )
    statuses = sorted(s.status for s in result.signals[1001])
    assert statuses == ["expired", "undated"]


def test_unrelated_titles_are_ignored_and_duplicates_collapse() -> None:
    result = signals_from_postings(
        [posting(9001), posting(9001), posting(9004, title="Senior Backend Engineer")],
        plan(),
        TODAY,
    )
    assert len(result.signals[1001]) == 1


def test_tech_keyword_in_posting_is_fit_evidence_with_excerpt() -> None:
    result = signals_from_postings([posting()], plan(), TODAY)
    [ev] = result.tech_evidence[1001]
    assert "Zendesk" in ev.claim and "Zendesk" in (ev.excerpt or "")
    assert ev.source_url == "https://jobs.example/9001"


def test_tech_keyword_requires_word_boundary() -> None:
    result = signals_from_postings([posting(description="We use Zendeskish tools")], plan(), TODAY)
    assert result.tech_evidence.get(1001, []) == []


def test_evidence_ids_are_stable() -> None:
    a = signals_from_postings([posting()], plan(), TODAY).evidence
    b = signals_from_postings([posting()], plan(), TODAY).evidence
    assert [e.id for e in a] == [e.id for e in b]


def test_a_funding_round_is_a_real_dated_event_not_a_metric_refresh() -> None:
    c = company(
        funding_last_fundraise_date="2026-10-24",
        funding_last_round_type="series_a",
        funding_total_usd=12_000_000.0,
    )
    sigs, evidence = signals_from_company(c, plan(signal_types=["recent_funding"]), TODAY)
    funding = by_type(sigs)["recent_funding"]
    assert funding.event_on == date(2026, 10, 24)
    assert funding.status == "active" and funding.age_days == 7
    assert "series_a" in funding.description and "$12,000,000" in funding.description
    [ev] = [e for e in evidence if e.id in funding.evidence_ids]
    assert ev.provider_ref == "crustdata:/company/search:funding.last_fundraise_date"
    assert ev.event_on == date(2026, 10, 24)


def test_no_funding_signal_without_a_fundraise_date() -> None:
    c = company(funding_last_fundraise_date=None)
    sigs, _ = signals_from_company(c, plan(signal_types=["recent_funding"]), TODAY)
    assert "recent_funding" not in by_type(sigs)


def test_a_funding_round_outside_the_signal_types_is_not_surfaced() -> None:
    c = company(funding_last_fundraise_date="2026-10-24")
    sigs, _ = signals_from_company(c, plan(signal_types=["active_hiring"]), TODAY)
    assert "recent_funding" not in by_type(sigs)


def test_a_hiring_signal_reads_job_postings_for_any_kind_of_buyer() -> None:
    assert wants_postings(plan(signal_types=["active_hiring"], tech_keywords=[]))
    assert wants_postings(plan(signal_types=["support_team_growth"], tech_keywords=[]))
    assert not wants_postings(plan(signal_types=["headcount_growth"], tech_keywords=[]))


def test_a_posting_counts_as_active_hiring_when_that_is_the_chosen_signal() -> None:
    p = plan(signal_types=["active_hiring"], tech_keywords=[])
    out = signals_from_postings([posting(title="Head of Support")], p, TODAY)
    assert [s.type for s in out.signals[1001]] == ["active_hiring"]
    assert out.signals[1001][0].window_days == 30
