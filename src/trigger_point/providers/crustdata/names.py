"""Resolve plan text to the exact values Crustdata holds, using its free autocomplete.

A name is only ever replaced by a suggestion that is the same words in different case. A near match
is not guessed: the name is kept and the plan says it was not recognised."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from trigger_point.providers.crustdata.client import CrustdataClient
from trigger_point.providers.crustdata.errors import CrustdataError

if TYPE_CHECKING:
    from trigger_point.mission.models import GTMPlan


def _words(text: str) -> list[str]:
    """Case, punctuation and the word "and" do not change which category a name is."""
    return [w for w in re.split(r"[^a-z0-9]+", text.casefold()) if w and w != "and"]


def resolve_names(
    client: CrustdataClient, field: str, names: list[str]
) -> tuple[list[str], list[str]]:
    resolved: list[str] = []
    notes: list[str] = []
    for name in names:
        queries = list(dict.fromkeys([name, name.replace("/", " and ")]))
        try:
            suggestions = [s for q in queries for s in client.autocomplete_company(field, q).data]
        except CrustdataError as exc:
            resolved.append(name)
            notes.append(f"{name!r} could not be checked against Crustdata ({exc.kind})")
            continue
        same = [s for s in suggestions if _words(s) == _words(name)]
        if not same:
            resolved.append(name)
            notes.append(f"{name!r} is not recognised by Crustdata; used as written")
            continue
        # The taxonomy can hold one idea under two spellings. The filter takes a list, so use both.
        same = list(dict.fromkeys(same))
        same.sort(key=lambda s: s.casefold() != name.casefold())
        resolved.extend(same)
        if same != [name]:
            notes.append(
                f"{name!r} written as {' / '.join(map(repr, same))}, as Crustdata spells it"
            )
    return list(dict.fromkeys(resolved)), notes


def canonical_plan(client: CrustdataClient, plan: GTMPlan) -> tuple[GTMPlan, list[str]]:
    """The plan with its industries and places spelled the way Crustdata matches them."""
    industries, notes = resolve_names(client, "basic_info.industries", list(plan.industries))
    places, more = resolve_names(client, "locations.headquarters", list(plan.places))
    return plan.model_copy(update={"industries": industries, "places": places}), notes + more
