"""A schools plan returns schools, not tutoring apps."""

import pytest

from trigger_point.mission.compiler import buyer_query


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (
            "CBSE schools in India with students in Classes 6 to 10 that teach maths using NCERT textbooks",
            "CBSE schools in India",
        ),
        ("Private schools in Mumbai that use tablets", "Private schools in Mumbai"),
        ("B2B SaaS companies scaling support teams", "B2B SaaS companies scaling support teams"),
        ("Software companies with support teams", "Software companies with support teams"),
    ],
)
def test_the_search_names_the_kind_of_organisation_only(query: str, expected: str) -> None:
    assert buyer_query(query) == expected
