"""The evaluation set must pass, and must be able to fail."""

from evals.run_evals import SUITES, run_all


def test_every_eval_case_passes() -> None:
    failed = [r for r in run_all() if not r["passed"]]
    assert failed == []


def test_each_suite_has_edge_cases_not_only_happy_paths() -> None:
    results = run_all()
    for suite in SUITES:
        kinds = {r["kind"] for r in results if r["suite"] == suite}
        assert len(kinds) >= 2, suite
