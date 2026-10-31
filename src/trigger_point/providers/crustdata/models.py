"""Typed Crustdata request/response models (API 2025-11-01) and normalised internal records.

Request vocabularies are allowlists taken from docs.crustdata.com; anything else
is rejected before an HTTP request exists, so LLM-proposed filters cannot reach the client.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator

Operator = Literal[
    "=", "!=", "<", "=<", ">", "=>", "in", "not_in", "is_null", "is_not_null", "(.)", "[.]"
]

ROLE_FUNCTIONS = (
    "accounting",
    "administrative",
    "arts_and_design",
    "business_development",
    "community_and_social_services",
    "consulting",
    "customer_success_and_support",
    "education",
    "engineering",
    "entrepreneurship",
    "finance",
    "healthcare_services",
    "human_resources",
    "information_technology",
    "legal",
    "marketing",
    "media_and_communication",
    "military_and_protective_services",
    "operations",
    "product_management",
    "program_and_project_management",
    "purchasing",
    "quality_assurance",
    "real_estate",
    "research",
    "sales",
    "support",
)
_PERIODS = ("1m", "3m", "6m", "12m")
FILTERABLE_FIELDS: frozenset[str] = frozenset(
    {
        "crustdata_company_id",
        "updated_at",
        "indexed_at",
        "basic_info.name",
        "basic_info.primary_domain",
        "basic_info.website",
        "basic_info.professional_network_url",
        "basic_info.company_type",
        "basic_info.status",
        "basic_info.year_founded",
        "basic_info.employee_count_range",
        "basic_info.markets",
        "basic_info.industries",
        "revenue.estimated.lower_bound_usd",
        "revenue.estimated.upper_bound_usd",
        "funding.total_investment_usd",
        "funding.last_round_amount_usd",
        "funding.last_fundraise_date",
        "funding.last_round_type",
        "funding.investors",
        "headcount.total",
        "headcount.largest_headcount_country",
        "locations.country",
        "locations.headquarters",
        "taxonomy.professional_network_industry",
        "taxonomy.professional_network_specialities",
        "taxonomy.categories",
        "taxonomy.primary_naics_detail.naics_code",
        "followers.count",
        "followers.six_months_growth_percent",
    }
    | {f"headcount.growth_{k}.{p}" for k in ("percent", "absolute") for p in _PERIODS}
    | {
        f"roles.{m}.{fn}"
        for m in ("distribution", "distribution_percent", "growth_6m", "growth_yoy")
        for fn in ROLE_FUNCTIONS
    }
)
SELECTABLE_GROUPS: frozenset[str] = frozenset(
    {
        "basic_info",
        "revenue",
        "headcount",
        "funding",
        "hiring",
        "locations",
        "taxonomy",
        "followers",
        "social_profiles",
        "software_reviews",
        "metadata",
        "updated_at",
        "indexed_at",
        "crustdata_company_id",
    }
)
SORTABLE_FIELDS: frozenset[str] = frozenset(
    {
        "crustdata_company_id",
        "updated_at",
        "basic_info.name",
        "basic_info.year_founded",
        "funding.total_investment_usd",
        "funding.last_round_amount_usd",
        "funding.last_fundraise_date",
        "headcount.total",
        "followers.count",
    }
)


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str
    type: Operator
    value: str | int | float | bool | list[str | int | float] | None

    @field_validator("field")
    @classmethod
    def _known_field(cls, v: str) -> str:
        if v not in FILTERABLE_FIELDS:
            raise ValueError(f"{v!r} is not a supported Crustdata company filter field")
        return v

    @model_validator(mode="after")
    def _value_matches_operator(self) -> Self:
        if self.type in ("in", "not_in") and not isinstance(self.value, list):
            raise ValueError(f"operator {self.type} requires a list value")
        if self.type in ("is_null", "is_not_null") and self.value is not None:
            raise ValueError(f"operator {self.type} requires value null")
        if self.type not in ("is_null", "is_not_null") and self.value is None:
            raise ValueError(f"operator {self.type} requires a value")
        return self


class ConditionGroup(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    op: Literal["and", "or"]
    conditions: list[Condition | ConditionGroup] = Field(min_length=1)


class SemanticSearch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1, max_length=4000)
    mode: Literal["hybrid", "lexical", "semantic"] = "hybrid"


class Sort(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str
    order: Literal["asc", "desc"]

    @field_validator("field")
    @classmethod
    def _sortable(cls, v: str) -> str:
        if v not in SORTABLE_FIELDS:
            raise ValueError(f"{v!r} is not sortable")
        return v


class CompanySearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    filters: Condition | ConditionGroup | None = None
    search: SemanticSearch | None = None
    cursor: str | None = None
    limit: int = Field(default=20, ge=1, le=1000)
    sorts: list[Sort] | None = None
    fields: list[str] | None = None

    @model_validator(mode="after")
    def _documented_constraints(self) -> Self:
        if self.filters is None and self.search is None:
            raise ValueError("company search needs filters or search")
        if self.search is not None and self.limit > 100:
            raise ValueError("ranked search returns at most 100 results per page")
        if self.search is not None and self.sorts:
            raise ValueError("sorts are not supported with ranked search")
        for f in self.fields or []:
            if f.split(".", 1)[0] not in SELECTABLE_GROUPS:
                raise ValueError(f"{f!r} is not a selectable search field")
        return self

    def to_body(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)

    def filter_groups(self) -> set[str]:
        def walk(node: Condition | ConditionGroup | None) -> set[str]:
            if node is None:
                return set()
            if isinstance(node, Condition):
                return {node.field.split(".", 1)[0]}
            return set().union(*(walk(c) for c in node.conditions))

        return walk(self.filters)


# ---- responses (unknown fields ignored, known fields typed, missing = None) ----


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


# Free lookup of the values Crustdata really holds for a text field. Matching on these is exact and
# case-sensitive, so a name is resolved here before a paid search uses it.
AUTOCOMPLETE_FIELDS: frozenset[str] = frozenset({"basic_info.industries", "locations.headquarters"})


class _Suggestion(_Lenient):
    value: str


class Suggestions(_Lenient):
    suggestions: list[_Suggestion] = []

    def values(self) -> list[str]:
        return [x.value for x in self.suggestions if x.value]


class BasicInfo(_Lenient):
    name: str | None = None
    primary_domain: str | None = None
    all_domains: list[str] | None = None
    website: str | None = None
    professional_network_url: str | None = None
    description: str | None = None
    company_type: str | None = None
    year_founded: int | str | None = None
    employee_count_range: str | None = None
    industries: list[str] | None = None


class CompanyIdentifyData(_Lenient):
    crustdata_company_id: int
    basic_info: BasicInfo | None = None


class IdentifyMatch(_Lenient):
    confidence_score: float
    company_data: CompanyIdentifyData


class IdentifyResult(_Lenient):
    matched_on: str
    match_type: str
    matches: list[IdentifyMatch]


class Headcount(_Lenient):
    total: int | None = None
    growth_percent: dict[str, float | None] | None = None


class Hiring(_Lenient):
    openings_count: int | None = None
    openings_growth_percent: dict[str, float | None] | None = None


class Funding(_Lenient):
    total_investment_usd: float | None = None
    last_round_amount_usd: float | None = None
    last_fundraise_date: str | None = None
    last_round_type: str | None = None


class Locations(_Lenient):
    country: str | None = None
    headquarters: str | None = None


class CompanyRecord(_Lenient):
    crustdata_company_id: int
    basic_info: BasicInfo | None = None
    headcount: Headcount | None = None
    hiring: Hiring | None = None
    funding: Funding | None = None
    locations: Locations | None = None
    updated_at: str | None = None


class SearchResponse(_Lenient):
    companies: list[CompanyRecord]
    next_cursor: str | None = None
    total_count: int | None = None


class EndpointEntry(_Lenient):
    path: str
    category: str | None = None
    status: str
    effective_rate_limit_rpm: int | None = None
    base_credits: float | None = None


class EndpointAccess(_Lenient):
    api_version: str | None = None
    endpoints: list[EndpointEntry]

    def is_enabled(self, path: str) -> bool:
        return any(e.path == path and e.status == "enabled" for e in self.endpoints)


# ---- normalised internal records ----


class Company(BaseModel):
    """Trigger Point's provider-neutral company record. Missing provider data stays None."""

    model_config = ConfigDict(frozen=True)

    provider: Literal["crustdata"] = "crustdata"
    provider_company_id: int
    name: str | None
    primary_domain: str | None
    all_domains: list[str] = Field(default_factory=list)
    website: str | None = None
    professional_network_url: str | None = None
    description: str | None = None
    employee_count_range: str | None = None
    industries: list[str] = Field(default_factory=list)
    headcount_total: int | None = None
    headcount_growth_6m_pct: float | None = None
    headcount_growth_12m_pct: float | None = None
    hiring_openings: int | None = None
    funding_last_round_type: str | None = None
    funding_last_fundraise_date: str | None = None
    funding_total_usd: float | None = None
    hq_country: str | None = None
    provider_updated_at: str | None = None
    retrieved_at: datetime
    source_endpoint: str


class CompanySearchPage(BaseModel):
    companies: list[Company]
    next_cursor: str | None
    total_count: int | None


def normalise_company(rec: CompanyRecord, retrieved_at: datetime, endpoint: str) -> Company:
    b = rec.basic_info or BasicInfo()
    growth = (rec.headcount.growth_percent if rec.headcount else None) or {}
    return Company(
        provider_company_id=rec.crustdata_company_id,
        name=b.name,
        primary_domain=(b.primary_domain or "").lower() or None,
        all_domains=[d.lower() for d in b.all_domains or []],
        website=b.website,
        professional_network_url=b.professional_network_url,
        description=b.description,
        employee_count_range=b.employee_count_range,
        industries=b.industries or [],
        headcount_total=rec.headcount.total if rec.headcount else None,
        headcount_growth_6m_pct=growth.get("6m"),
        headcount_growth_12m_pct=growth.get("12m"),
        hiring_openings=rec.hiring.openings_count if rec.hiring else None,
        funding_last_round_type=(rec.funding.last_round_type or None) if rec.funding else None,
        funding_last_fundraise_date=rec.funding.last_fundraise_date if rec.funding else None,
        funding_total_usd=rec.funding.total_investment_usd if rec.funding else None,
        hq_country=rec.locations.country if rec.locations else None,
        provider_updated_at=rec.updated_at,
        retrieved_at=retrieved_at,
        source_endpoint=endpoint,
    )


# ---- Job search (/job/search) and Person search (/person/search) ----
# Field allowlists copied from docs.crustdata.com API reference (2025-11-01).

JOB_FILTERABLE_FIELDS: frozenset[str] = frozenset(
    {
        "job_details.title",
        "job_details.category",
        "job_details.workplace_type",
        "job_details.employment_type",
        "job_details.reposted_job",
        "job_details.url",
        "company.basic_info.company_id",
        "company.basic_info.name",
        "company.basic_info.primary_domain",
        "company.basic_info.industries",
        "location.country",
        "location.city",
        "content.description",
        "crustdata_job_id",
        "metadata.date_added",
        "metadata.date_updated",
    }
)
JOB_SELECTABLE_GROUPS: frozenset[str] = frozenset(
    {"crustdata_job_id", "job_details", "company", "location", "content", "metadata"}
)
PERSON_FILTERABLE_FIELDS: frozenset[str] = frozenset(
    {
        "crustdata_person_id",
        "experience.employment_details.current.company_id",
        "experience.employment_details.current.title",
        "experience.employment_details.current.seniority_level",
        "experience.employment_details.current.function_category",
        "experience.employment_details.current.start_date",
    }
)
# Never request contact data here: it is a separate, opt-in, per-contact-billed step (person enrich).
PERSON_RESPONSE_FIELDS = [
    "crustdata_person_id",
    "basic_profile.name",
    "basic_profile.current_title",
    "experience.employment_details.current",
    "social_handles.professional_network_identifier.profile_url",
    "metadata.updated_at",
]


def _check_operator_value(op: str, value: object) -> None:
    if op in ("in", "not_in") and not isinstance(value, list):
        raise ValueError(f"operator {op} requires a list value")
    if op in ("is_null", "is_not_null") and value is not None:
        raise ValueError(f"operator {op} requires value null")
    if op not in ("is_null", "is_not_null") and value is None:
        raise ValueError(f"operator {op} requires a value")


class JobCondition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str
    type: Operator
    value: str | int | float | bool | list[str | int | float] | None

    @field_validator("field")
    @classmethod
    def _known_field(cls, v: str) -> str:
        if v not in JOB_FILTERABLE_FIELDS:
            raise ValueError(f"{v!r} is not a supported Crustdata job filter field")
        return v

    @model_validator(mode="after")
    def _value_matches_operator(self) -> Self:
        _check_operator_value(self.type, self.value)
        return self


class JobConditionGroup(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    op: Literal["and", "or"]
    conditions: list[JobCondition | JobConditionGroup] = Field(min_length=1)


class JobSort(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: Literal["metadata.date_added", "metadata.date_updated"]
    order: Literal["asc", "desc"]


class JobSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    filters: JobCondition | JobConditionGroup
    limit: int = Field(default=20, ge=1, le=1000)
    sorts: list[JobSort] | None = None
    fields: list[str] | None = None
    cursor: str | None = None

    @model_validator(mode="after")
    def _fields_known(self) -> Self:
        for f in self.fields or []:
            if f.split(".", 1)[0] not in JOB_SELECTABLE_GROUPS:
                raise ValueError(f"{f!r} is not a selectable job field")
        return self

    def to_body(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class PersonCondition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str
    type: Operator
    value: str | int | float | bool | list[str | int | float] | None

    @field_validator("field")
    @classmethod
    def _known_field(cls, v: str) -> str:
        if v not in PERSON_FILTERABLE_FIELDS:
            raise ValueError(f"{v!r} is not a supported Crustdata person filter field")
        return v

    @model_validator(mode="after")
    def _value_matches_operator(self) -> Self:
        _check_operator_value(self.type, self.value)
        return self


class PersonConditionGroup(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    op: Literal["and", "or"]
    conditions: list[PersonCondition | PersonConditionGroup] = Field(min_length=1)


class PersonSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    filters: PersonCondition | PersonConditionGroup
    limit: int = Field(default=20, ge=1, le=1000)
    cursor: str | None = None

    def to_body(self) -> dict[str, Any]:
        body = self.model_dump(mode="json", exclude_none=True)
        body["fields"] = list(PERSON_RESPONSE_FIELDS)
        return body


class _JobDetails(_Lenient):
    title: str | None = None
    category: str | None = None
    url: str | None = None


class _JobCompanyBasic(_Lenient):
    crustdata_company_id: int | None = None
    company_id: int | None = None  # filter-side name; accepted defensively
    name: str | None = None
    primary_domain: str | None = None


class _JobCompany(_Lenient):
    basic_info: _JobCompanyBasic | None = None


class _JobMetadata(_Lenient):
    date_added: str | None = None
    date_updated: str | None = None


class _JobContent(_Lenient):
    description: str | None = None


class JobListing(_Lenient):
    crustdata_job_id: int | None = None
    job_details: _JobDetails | None = None
    company: _JobCompany | None = None
    metadata: _JobMetadata | None = None
    content: _JobContent | None = None


class JobSearchResponse(_Lenient):
    job_listings: list[JobListing]
    next_cursor: str | None = None
    total_count: int | None = None


class _PersonBasic(_Lenient):
    name: str | None = None
    current_title: str | None = None


class _Employment(_Lenient):
    title: str | None = None
    crustdata_company_id: int | None = None
    start_date: str | None = None


class _EmploymentDetails(_Lenient):
    current: list[_Employment] | None = None


class _Experience(_Lenient):
    employment_details: _EmploymentDetails | None = None


class _NetworkId(_Lenient):
    profile_url: str | None = None


class _Social(_Lenient):
    professional_network_identifier: _NetworkId | None = None


class _PersonMeta(_Lenient):
    updated_at: str | None = None


class _Contact(_Lenient):
    """`contact` appears only on a person enrich response, never on our search. Items are a bare
    string or an object with the value and a deliverability status; both are accepted."""

    business_emails: list[Any] | None = None
    personal_emails: list[Any] | None = None
    phone_numbers: list[Any] | None = None


class PersonProfile(_Lenient):
    crustdata_person_id: int
    basic_profile: _PersonBasic | None = None
    experience: _Experience | None = None
    social_handles: _Social | None = None
    metadata: _PersonMeta | None = None
    contact: _Contact | None = None


class PersonSearchResponse(_Lenient):
    profiles: list[PersonProfile]
    next_cursor: str | None = None
    total_count: int | None = None


def _iso_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


class JobPosting(BaseModel):
    """A normalised posting. `posted_on` is the event date; `last_seen_on` is the provider's
    last refresh, the best available evidence the posting was still listed."""

    model_config = ConfigDict(frozen=True)

    provider_job_id: int | None
    company_id: int | None
    company_name: str | None
    title: str | None
    category: str | None
    url: str | None
    posted_on: date | None
    last_seen_on: date | None
    description: str | None
    retrieved_at: datetime


class JobSearchPage(BaseModel):
    postings: list[JobPosting]
    next_cursor: str | None
    total_count: int | None


class ContactPoint(BaseModel):
    """One email or phone number Crustdata supplied for a person. Never copied into evidence,
    drafts, prompts or event text; it is shown to the user only."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["email", "phone"]
    label: Literal["business", "personal"] | None = None
    value: str
    status: str | None = None  # the provider's deliverability verdict, as given


_EMAIL = re.compile(r"^[^\s@<>\"',;]+@[^\s@<>\"',;]+\.[^\s@<>\"',;]+$")
_PHONE = re.compile(r"^\+?[0-9][0-9 ()\-.]{5,19}$")
MAX_CONTACTS_PER_KIND = 5
_DEAD_EMAIL = {"invalid", "undeliverable", "bounced"}


def _contact_points(c: _Contact | None) -> list[ContactPoint]:
    """Valid, de-duplicated contact points. Anything malformed is dropped, not repaired."""
    if c is None:
        return []
    out: list[ContactPoint] = []
    groups: list[
        tuple[Literal["email", "phone"], Literal["business", "personal"] | None, list[Any] | None]
    ] = [
        ("email", "business", c.business_emails),
        ("email", "personal", c.personal_emails),
        ("phone", None, c.phone_numbers),
    ]
    for kind, label, items in groups:
        seen: set[str] = set()
        raw: Any
        status: Any
        for item in items or []:
            if isinstance(item, str):
                raw, status = item, None
            elif isinstance(item, dict):
                raw = item.get(kind) or item.get("email") or item.get("phone") or item.get("value")
                status = item.get("status") or item.get("verification_status")
            else:
                continue
            value = raw.strip() if isinstance(raw, str) else ""
            if kind == "email" and str(status or "").strip().lower() in _DEAD_EMAIL:
                continue  # an address the provider says cannot receive mail is not worth showing
            valid = _EMAIL.match(value) if kind == "email" else _PHONE.match(value)
            key = value.lower()
            if not valid or key in seen or len(seen) >= MAX_CONTACTS_PER_KIND:
                continue
            seen.add(key)
            out.append(
                ContactPoint(
                    kind=kind, label=label, value=value, status=str(status) if status else None
                )
            )
    return out


class PersonRecord(BaseModel):
    """Person data for the stated purpose. `contact` is empty unless contact details were bought
    from Crustdata (person enrich); our search request never asks for them."""

    model_config = ConfigDict(frozen=True)

    provider_person_id: int
    name: str | None
    current_title: str | None
    current_company_ids: list[int]
    current_titles: list[str]
    current_role_start: str | None
    profile_url: str | None
    provider_updated_at: str | None
    retrieved_at: datetime
    contact: list[ContactPoint] = Field(default_factory=list)


class PersonSearchPage(BaseModel):
    people: list[PersonRecord]
    next_cursor: str | None
    total_count: int | None


MAX_DESCRIPTION_CHARS = 4000


def normalise_job(listing: JobListing, retrieved_at: datetime) -> JobPosting:
    d = listing.job_details or _JobDetails()
    b = (listing.company.basic_info if listing.company else None) or _JobCompanyBasic()
    m = listing.metadata or _JobMetadata()
    desc = listing.content.description if listing.content else None
    return JobPosting(
        provider_job_id=listing.crustdata_job_id,
        company_id=b.crustdata_company_id if b.crustdata_company_id is not None else b.company_id,
        company_name=b.name,
        title=d.title,
        category=d.category,
        url=d.url,
        posted_on=_iso_date(m.date_added),
        last_seen_on=_iso_date(m.date_updated),
        description=desc[:MAX_DESCRIPTION_CHARS] if desc else None,
        retrieved_at=retrieved_at,
    )


def normalise_person(p: PersonProfile, retrieved_at: datetime) -> PersonRecord:
    current = (
        (p.experience.employment_details.current or [])
        if (p.experience and p.experience.employment_details)
        else []
    )
    basic = p.basic_profile or _PersonBasic()
    starts = [e.start_date for e in current if e.start_date]
    return PersonRecord(
        provider_person_id=p.crustdata_person_id,
        name=basic.name,
        current_title=basic.current_title or (current[0].title if current else None),
        current_company_ids=[
            e.crustdata_company_id for e in current if e.crustdata_company_id is not None
        ],
        current_titles=[e.title for e in current if e.title],
        current_role_start=starts[0] if starts else None,
        profile_url=(
            p.social_handles.professional_network_identifier.profile_url
            if p.social_handles and p.social_handles.professional_network_identifier
            else None
        ),
        provider_updated_at=p.metadata.updated_at if p.metadata else None,
        retrieved_at=retrieved_at,
        contact=_contact_points(p.contact),
    )


# Contact lookup: POST /person/contact/enrich, from docs.crustdata.com/person-docs/contact/enrich.
# Business emails and phone numbers only; personal emails are not requested. UNVERIFIED: never
# called live, and the endpoint is documented as enterprise-only (a 403 is handled as "unavailable").
CONTACT_FIELDS = ("contact.business_emails", "contact.phone_numbers")
MAX_CONTACT_BATCH = 25
MIN_CONTACT_CONFIDENCE = 0.99


class ContactEnrichRequest(BaseModel):
    """People to look up, as (provider person id, professional-network profile URL)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    targets: tuple[tuple[int, str], ...] = Field(min_length=1, max_length=MAX_CONTACT_BATCH)

    @field_validator("targets")
    @classmethod
    def _http_urls(cls, v: tuple[tuple[int, str], ...]) -> tuple[tuple[int, str], ...]:
        for _, url in v:
            if not re.match(r"^https?://\S+$", url):
                raise ValueError("a profile URL must be an http(s) link")
        return v

    def to_body(self) -> dict[str, Any]:
        return {
            "professional_network_profile_urls": [url for _, url in self.targets],
            "fields": list(CONTACT_FIELDS),
        }


class _ContactPerson(_Lenient):
    crustdata_person_id: int | None = None
    contact: _Contact | None = None


class _ContactMatch(_Lenient):
    confidence_score: float | None = None
    person_data: _ContactPerson | None = None


class _ContactEntry(_Lenient):
    matched_on: str | None = None
    match_type: str | None = None
    matches: list[_ContactMatch] = Field(default_factory=list)


class ContactEnrichResponse(RootModel[list[_ContactEntry]]):
    """The response is a top-level array with one entry per identifier we sent."""


def normalise_contacts(
    req: ContactEnrichRequest, resp: ContactEnrichResponse
) -> dict[int, list[ContactPoint]]:
    """Contact points by our person id. A match is used only when it is a confident one and does
    not name a different person than the one we asked about; otherwise the person gets nothing."""
    by_url = {url: pid for pid, url in req.targets}
    asked = set(by_url.values())
    out: dict[int, list[ContactPoint]] = {}
    for entry in resp.root:
        pid = by_url.get(entry.matched_on or "")
        for m in entry.matches:
            if (m.confidence_score or 0) < MIN_CONTACT_CONFIDENCE or m.person_data is None:
                continue
            got = m.person_data.crustdata_person_id
            if pid is None and got in asked:
                pid = got  # the provider may normalise the URL it echoes back
            if pid is None or (got is not None and got != pid):
                continue
            points = _contact_points(m.person_data.contact)
            if points:
                out[pid] = points
            break
    return out


# ---- Social post search (/social_post/search) ----
# Billed per post returned, so a request names its author, topic and date window up front.
# It never asks for names, headlines, reactors or comments: a post's text, its public URL and
# the author's role and employer are all the evidence a signal needs.

POST_FILTERABLE_FIELDS: frozenset[str] = frozenset(
    {
        "text",
        "hashtags",
        "post_type",
        "date_posted",
        "actor.actor_type",
        "actor.crustdata_entity_id",
        "actor.title",
        "actor.company_name",
        "actor.location.city",
        "actor.location.state",
        "actor.location.country",
    }
)
POST_RESPONSE_FIELDS: tuple[str, ...] = (
    "share_url",
    "date_posted",
    "text",
    "post_type",
    "actor.crustdata_entity_id",
    "actor.title",
    "actor.company_name",
)
POST_SORT_FIELDS = ("date_posted", "engagement.total_reactions")
MAX_POST_CHARS = 2000


class PostCondition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str
    type: Operator
    value: str | int | float | bool | list[str | int | float] | None

    @field_validator("field")
    @classmethod
    def _known_field(cls, v: str) -> str:
        if v not in POST_FILTERABLE_FIELDS:
            raise ValueError(f"{v!r} is not a supported Crustdata post filter field")
        return v

    @model_validator(mode="after")
    def _value_matches_operator(self) -> Self:
        _check_operator_value(self.type, self.value)
        return self


class PostConditionGroup(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    op: Literal["and", "or"]
    conditions: list[PostCondition | PostConditionGroup] = Field(min_length=1)


class PostSort(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str
    order: Literal["asc", "desc"]

    @field_validator("field")
    @classmethod
    def _known_field(cls, v: str) -> str:
        if v not in POST_SORT_FIELDS:
            raise ValueError(f"{v!r} is not a supported post sort field")
        return v


class PostSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    filters: PostCondition | PostConditionGroup
    limit: int = Field(default=5, ge=1, le=25)
    sorts: list[PostSort] | None = None
    fields: list[str] | None = None

    @model_validator(mode="after")
    def _fields_selectable(self) -> Self:
        for f in self.fields or []:
            if f not in POST_RESPONSE_FIELDS:
                raise ValueError(f"{f!r} is not a selectable post field")
        return self

    def to_body(self) -> dict[str, Any]:
        body = self.model_dump(mode="json", exclude_none=True)
        body["fields"] = list(self.fields or POST_RESPONSE_FIELDS)
        body.setdefault("sorts", [{"field": "date_posted", "order": "desc"}])
        return body


class _PostActor(_Lenient):
    crustdata_entity_id: int | None = None
    title: str | None = None
    company_name: str | None = None


class _Post(_Lenient):
    share_url: str | None = None
    date_posted: str | None = None
    text: str | None = None
    post_type: str | None = None
    actor: _PostActor | None = None


class PostSearchResponse(_Lenient):
    posts: list[_Post]
    next_cursor: str | None = None
    total_count: int | None = None


class SocialPost(BaseModel):
    """A public post, reduced to what a signal needs. There is no name or headline on purpose."""

    model_config = ConfigDict(frozen=True)

    post_url: str | None
    text: str
    posted_on: date | None
    post_type: str | None
    author_id: int | None
    author_title: str | None
    author_company: str | None
    retrieved_at: datetime
    source_endpoint: str = "/social_post/search"


class PostSearchPage(BaseModel):
    posts: list[SocialPost]
    next_cursor: str | None
    total_count: int | None


def normalise_post(p: _Post, retrieved_at: datetime) -> SocialPost:
    actor = p.actor or _PostActor()
    return SocialPost(
        post_url=p.share_url,
        text=(p.text or "")[:MAX_POST_CHARS],
        posted_on=_iso_date(p.date_posted),
        post_type=p.post_type,
        author_id=actor.crustdata_entity_id,
        author_title=actor.title,
        author_company=actor.company_name,
        retrieved_at=retrieved_at,
    )
