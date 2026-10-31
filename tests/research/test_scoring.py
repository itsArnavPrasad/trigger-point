import math
from datetime import date

import pytest

from tests.research.factories import company, plan
from trigger_point.research.scoring import (
    SCORE_VERSION,
    WEIGHTS,
    PeopleOutcome,
    rank,
    score_account,
)
from trigger_point.research.signals import Signal


def sig(
    kind: str = "support_team_growth",
    age: int | None = 10,
    status: str = "active",
    strength: float = 0.6,
    window: int = 30,
    cid: int = 1001,
) -> Signal:
    return Signal(
        id=f"s-{kind}-{age}-{strength}",
        account_id=cid,
        type=kind,
        description="d",
        value=None,
        event_on=date(2026, 10, 21) if age is not None else None,
        as_of=None,
        age_days=age,
        window_days=window,
        status=status,  # type: ignore[arg-type]
        strength=strength,
        evidence_ids=["ev_x"],
    )


FOUND = PeopleOutcome(searched=True, best_match_confidence=1.0)
NOT_SEARCHED = PeopleOutcome(searched=False)
NONE_FOUND = PeopleOutcome(searched=True, best_match_confidence=None)


def test_weights_are_versioned_and_sum_to_one() -> None:
    assert SCORE_VERSION == "score-v1"
    assert math.isclose(sum(WEIGHTS.values()), 1.0)


def test_strong_fit_recent_signal_buyer_found_qualifies() -> None:
    s = score_account(
        company(), [sig()], tech_hits=1, people=FOUND, plan=plan(), signals_collected=True
    )
    assert s.status == "qualified" and s.rejections == []
    assert s.components["fit"].value == 100 and s.components["timing"].value > 0
    assert s.coverage == 1.0 and 0 < s.total <= 100
    assert s.version == "score-v1"


def test_timing_formula_matches_spec() -> None:
    s = score_account(
        company(),
        [sig(age=10, strength=0.6, window=30)],
        tech_hits=0,
        people=FOUND,
        plan=plan(),
        signals_collected=True,
    )
    expected = 100 * (1 - (1 - 0.6 * math.exp(-10 / 15)))
    assert s.components["timing"].value == pytest.approx(expected, abs=0.01)


def test_strong_fit_stale_signal_is_rejected_no_fresh_why_now() -> None:
    s = score_account(
        company(),
        [sig(age=45, status="expired")],
        tech_hits=1,
        people=FOUND,
        plan=plan(),
        signals_collected=True,
    )
    assert s.status == "rejected" and "no_fresh_why_now" in s.rejections
    assert s.components["timing"].value == 0


def test_undated_signals_never_create_timing() -> None:
    s = score_account(
        company(),
        [sig(age=None, status="undated")],
        tech_hits=0,
        people=FOUND,
        plan=plan(),
        signals_collected=True,
    )
    assert s.components["timing"].value == 0 and "no_fresh_why_now" in s.rejections


def test_weak_fit_with_exciting_signal_scores_below_strong_fit() -> None:
    weak = score_account(
        company(hq_country="BRA", employee_count_range="10001+"),
        [sig(strength=1.0, age=1)],
        tech_hits=0,
        people=FOUND,
        plan=plan(),
        signals_collected=True,
    )
    strong = score_account(
        company(),
        [sig(strength=0.6, age=10)],
        tech_hits=1,
        people=FOUND,
        plan=plan(),
        signals_collected=True,
    )
    assert weak.components["fit"].value == 0
    assert strong.total > weak.total


def test_unknown_fit_fields_lower_coverage_not_score_inflation() -> None:
    s = score_account(
        company(hq_country=None, employee_count_range=None),
        [sig()],
        tech_hits=0,
        people=FOUND,
        plan=plan(tech_keywords=[]),
        signals_collected=True,
    )
    assert s.components["fit"].known is False and s.components["fit"].value is None
    assert s.coverage == pytest.approx(1 - WEIGHTS["fit"])
    assert s.status == "insufficient_evidence"


def test_no_buyer_after_search_is_a_hard_rejection() -> None:
    s = score_account(
        company(), [sig()], tech_hits=0, people=NONE_FOUND, plan=plan(), signals_collected=True
    )
    assert "no_relevant_buyer" in s.rejections and s.components["reachability"].value == 0


def test_people_not_searched_is_unknown_not_rejected() -> None:
    s = score_account(
        company(), [sig()], tech_hits=0, people=NOT_SEARCHED, plan=plan(), signals_collected=True
    )
    assert s.components["reachability"].known is False
    assert s.status == "insufficient_evidence" and s.rejections == []


def test_identity_unresolved_rejects() -> None:
    s = score_account(
        company(primary_domain=None),
        [sig()],
        tech_hits=0,
        people=FOUND,
        plan=plan(),
        signals_collected=True,
    )
    assert "identity_unresolved" in s.rejections


def test_missing_tech_evidence_is_unknown_not_zero() -> None:
    with_tech = score_account(
        company(), [sig()], tech_hits=1, people=FOUND, plan=plan(), signals_collected=True
    )
    without = score_account(
        company(), [sig()], tech_hits=0, people=FOUND, plan=plan(), signals_collected=True
    )
    assert with_tech.components["fit"].value == without.components["fit"].value == 100
    assert "tech" in with_tech.components["fit"].detail


def test_every_component_explains_itself() -> None:
    s = score_account(
        company(), [sig()], tech_hits=1, people=FOUND, plan=plan(), signals_collected=True
    )
    assert all(c.detail for c in s.components.values())


def test_rank_is_deterministic_with_tiebreak() -> None:
    a = (
        1002,
        score_account(
            company(1002),
            [sig(cid=1002)],
            tech_hits=0,
            people=FOUND,
            plan=plan(),
            signals_collected=True,
        ),
    )
    b = (
        1001,
        score_account(
            company(1001), [sig()], tech_hits=0, people=FOUND, plan=plan(), signals_collected=True
        ),
    )
    assert [cid for cid, _ in rank([a, b])] == [1001, 1002]
