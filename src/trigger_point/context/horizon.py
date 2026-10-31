"""The time frame a goal implies. "10 meetings next week" means one week, so nobody types it twice.

A user statement, never a sourced fact: the label says whether it came from the goal or is the
default. Nothing is guessed beyond the patterns below."""

from __future__ import annotations

import re

DEFAULT = "15 days (default, none stated)"
_UNITS = r"(day|week|month|quarter|year)s?"
_IN_N = re.compile(
    rf"\b(?:in|within|over|for|during)\s+(?:the\s+)?(?:next|coming|first)?\s*(\d+)\s*[- ]?{_UNITS}\b"
)
_N_UNIT = re.compile(rf"\b(\d+)[- ]{_UNITS}\b")
_ONE = re.compile(rf"\b(?:this|next|coming|upcoming|a|one)\s+{_UNITS}\b")
_BY_MONTH = re.compile(
    r"\bby\s+(?:the\s+end\s+of\s+)?(january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\b"
)
_WORDS = {"two": 2, "three": 3, "four": 4, "six": 6, "ten": 10, "twelve": 12}
_WORD_N = re.compile(
    rf"\b(?:in|within|over|for)\s+(?:the\s+)?(?:next\s+)?({'|'.join(_WORDS)})\s+{_UNITS}\b"
)


def _label(n: int, unit: str) -> str:
    return f"{n} {unit}{'' if n == 1 else 's'} (from your goal)"


def horizon_from_goal(goal: str) -> str:
    text = " ".join(goal.casefold().split())
    if m := _IN_N.search(text) or _N_UNIT.search(text):
        n = int(m.group(1))
        if 0 < n <= 999:
            return _label(n, m.group(2))
    if m := _WORD_N.search(text):
        return _label(_WORDS[m.group(1)], m.group(2))
    if m := _ONE.search(text):
        return _label(1, m.group(1))
    if m := _BY_MONTH.search(text):
        return f"by {m.group(1).capitalize()} (from your goal)"
    return DEFAULT
