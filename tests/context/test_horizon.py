import pytest

from trigger_point.context.horizon import DEFAULT, horizon_from_goal


@pytest.mark.parametrize(
    ("goal", "expected"),
    [
        ("Book 10 meetings in the coming week", "1 week (from your goal)"),
        ("book 10 meetings next week", "1 week (from your goal)"),
        ("Get 5 demos within 30 days", "30 days (from your goal)"),
        ("10 meetings in the next 2 weeks", "2 weeks (from your goal)"),
        ("a 90-day pilot pipeline", "90 days (from your goal)"),
        ("meetings within two weeks", "2 weeks (from your goal)"),
        ("Hit 20 calls this month", "1 month (from your goal)"),
        ("book meetings by December", "by December (from your goal)"),
        ("Book meetings with B2B SaaS companies", DEFAULT),
        ("get 10 meetings", DEFAULT),
        ("", DEFAULT),
    ],
)
def test_the_goal_sets_the_time_horizon(goal: str, expected: str) -> None:
    assert horizon_from_goal(goal) == expected
