"""Contact details are optional, validated, shown to the user only, and never requested by our search."""

from datetime import UTC, datetime

import httpx
import pytest
from pydantic import ValidationError

from tests.research.factories import company, person
from trigger_point.providers.crustdata.client import CreditBudget, CrustdataClient
from trigger_point.providers.crustdata.models import (
    PERSON_RESPONSE_FIELDS,
    ContactEnrichRequest,
    ContactEnrichResponse,
    PersonProfile,
    normalise_contacts,
    normalise_person,
)
from trigger_point.providers.crustdata.replay import RecordingTransport
from trigger_point.research.service import _person_evidence

NOW = datetime(2026, 10, 31, tzinfo=UTC)


def profile(contact: object) -> PersonProfile:
    return PersonProfile.model_validate(
        {
            "crustdata_person_id": 9,
            "basic_profile": {"name": "Asha Example", "current_title": "Head of Academics"},
            "contact": contact,
        }
    )


def test_a_person_without_contact_has_none_and_nothing_is_invented() -> None:
    assert normalise_person(profile(None), NOW).contact == []
    assert normalise_person(profile({}), NOW).contact == []


def test_emails_and_phones_are_read_from_strings_or_objects_with_their_status() -> None:
    rec = normalise_person(
        profile(
            {
                "business_emails": [
                    {"email": "asha@school.example", "status": "verified"},
                    "ops@school.example",
                ],
                "personal_emails": ["asha@mail.example"],
                "phone_numbers": ["+91 00000 00101"],
            }
        ),
        NOW,
    )
    by = {(c.kind, c.label, c.value): c.status for c in rec.contact}
    assert by[("email", "business", "asha@school.example")] == "verified"
    assert by[("email", "business", "ops@school.example")] is None
    assert ("email", "personal", "asha@mail.example") in by
    assert ("phone", None, "+91 00000 00101") in by


def test_malformed_duplicate_and_excess_values_are_dropped_not_repaired() -> None:
    rec = normalise_person(
        profile(
            {
                "business_emails": [
                    "not an email",
                    "a@b",
                    "x@y.example",
                    "X@Y.example",
                    "<script>@evil.example",
                    42,
                    None,
                ]
                + [f"p{i}@s.example" for i in range(10)],
                "phone_numbers": ["call me", "12", "+91 22 5550 0101"],
            }
        ),
        NOW,
    )
    emails = [c.value for c in rec.contact if c.kind == "email"]
    assert emails[0] == "x@y.example" and len(emails) == 5 and "X@Y.example" not in emails
    assert all("<" not in e and " " not in e for e in emails)
    assert [c.value for c in rec.contact if c.kind == "phone"] == ["+91 22 5550 0101"]


def test_our_person_search_never_asks_for_contact_fields() -> None:
    assert not any("contact" in f or "email" in f or "phone" in f for f in PERSON_RESPONSE_FIELDS)


def test_contact_never_reaches_evidence() -> None:
    p = normalise_person(
        profile(
            {"business_emails": ["asha@school.example"], "phone_numbers": ["+91 22 5550 0101"]}
        ),
        NOW,
    )
    ev = _person_evidence(
        type("M", (), {"person": p})(),  # a PersonaMatch needs only `.person` here
        company(),
    ).model_dump_json()
    assert "asha@school.example" not in ev and "5550" not in ev
    assert person().contact == []


URL = "https://www.linkedin.com/in/asha-example"


def entry(
    url: str = URL, pid: int | None = 7, confidence: float = 1.0, contact: object = None
) -> dict[str, object]:
    """Shaped like the example on docs.crustdata.com/person-docs/contact/enrich."""
    return {
        "matched_on": url,
        "match_type": "professional_network_profile_url",
        "matches": [
            {
                "confidence_score": confidence,
                "person_data": {
                    "crustdata_person_id": pid,
                    "contact": contact
                    if contact is not None
                    else {
                        "business_emails": [
                            {"email": "asha@school.example", "status": "deliverable"}
                        ],
                        "phone_numbers": ["+1 415-555-0100"],
                        "phone_numbers_info": [
                            {"country_code": "+1", "phone_number": "4155550100"}
                        ],
                    },
                },
            }
        ],
    }


def lookup(
    *entries: dict[str, object], targets: tuple[tuple[int, str], ...] = ((7, URL),)
) -> dict[int, list]:
    req = ContactEnrichRequest(targets=targets)
    return normalise_contacts(req, ContactEnrichResponse.model_validate(list(entries)))


def test_the_request_asks_for_business_email_and_phone_only() -> None:
    assert ContactEnrichRequest(targets=((7, URL),)).to_body() == {
        "professional_network_profile_urls": [URL],
        "fields": ["contact.business_emails", "contact.phone_numbers"],
    }


def test_the_request_rejects_non_http_links_and_oversized_batches() -> None:
    with pytest.raises(ValidationError):
        ContactEnrichRequest(targets=((7, "javascript:alert(1)"),))
    with pytest.raises(ValidationError):
        ContactEnrichRequest(targets=tuple((i, f"https://x.example/{i}") for i in range(26)))


def test_a_documented_response_gives_the_person_their_email_and_phone() -> None:
    [pt_email, pt_phone] = lookup(entry())[7]
    assert (pt_email.kind, pt_email.label, pt_email.value, pt_email.status) == (
        "email",
        "business",
        "asha@school.example",
        "deliverable",
    )
    assert (pt_phone.kind, pt_phone.value) == ("phone", "+1 415-555-0100")


def test_a_weak_match_or_a_different_person_gets_no_contact_details() -> None:
    assert lookup(entry(confidence=0.6)) == {}
    assert lookup(entry(pid=999)) == {}  # the provider matched someone we did not ask about
    assert lookup(entry(url="https://www.linkedin.com/in/someone-else", pid=None)) == {}


def test_an_unmatched_person_and_dead_addresses_give_nothing() -> None:
    assert (
        lookup({"matched_on": URL, "match_type": "professional_network_profile_url", "matches": []})
        == {}
    )
    dead = {
        "business_emails": [{"email": "gone@school.example", "status": "invalid"}],
        "phone_numbers": [],
    }
    assert lookup(entry(contact=dead)) == {}


def test_the_provider_may_echo_a_normalised_url_and_we_still_match_by_person_id() -> None:
    [pts] = lookup(entry(url="https://linkedin.com/in/asha-example/", pid=7)).values()
    assert pts[0].value == "asha@school.example"


def test_the_client_returns_contacts_and_books_the_credits_the_provider_reports() -> None:
    seen: dict[str, object] = {}

    def handler(r: httpx.Request) -> httpx.Response:
        seen["path"], seen["body"] = r.url.path, r.content
        return httpx.Response(200, json=[entry()], headers={"x-credits-used": "3"})

    budget = CreditBudget(10)
    client = CrustdataClient(
        httpx.Client(transport=httpx.MockTransport(handler)),
        "k",
        budget,
        mode="replay",
        sleep=lambda _s: None,
    )
    res = client.enrich_contacts(ContactEnrichRequest(targets=((7, URL),)))
    assert seen["path"] == "/person/contact/enrich"
    assert [c.value for c in res.data[7]] == ["asha@school.example", "+1 415-555-0100"]
    assert res.receipt.credits_used == 3 and budget.spent == 3 and res.receipt.result_count == 1


def test_the_recorder_never_writes_contact_responses_into_fixtures(tmp_path) -> None:  # type: ignore[no-untyped-def]
    inner = httpx.MockTransport(
        lambda r: httpx.Response(
            200, json=[entry()] if "contact" in r.url.path else {"profiles": []}
        )
    )
    http = httpx.Client(transport=RecordingTransport(inner, tmp_path))
    http.post(
        "https://api.crustdata.com/person/contact/enrich",
        json={"professional_network_profile_urls": [URL]},
    )
    assert not (tmp_path / "person_contact_enrich").exists()
    http.post("https://api.crustdata.com/person/search", json={"filters": {}})
    assert (tmp_path / "person_search").exists()
