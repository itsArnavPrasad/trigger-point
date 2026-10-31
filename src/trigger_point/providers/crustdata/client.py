"""Crustdata REST client: allowlisted endpoints, budget pre-flight (fails closed), bounded
retries for read-only calls, a read cache, and a receipt for every call (including failures)."""

from __future__ import annotations

import hashlib
import json
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Generic, TypeVar

import httpx
from pydantic import TypeAdapter, ValidationError

from trigger_point.config import Mode
from trigger_point.providers.crustdata.errors import CrustdataError, error_from_response
from trigger_point.providers.crustdata.models import (
    CompanySearchPage,
    CompanySearchRequest,
    ContactEnrichRequest,
    ContactEnrichResponse,
    ContactPoint,
    EndpointAccess,
    IdentifyResult,
    JobSearchPage,
    JobSearchRequest,
    JobSearchResponse,
    PersonSearchPage,
    PersonSearchRequest,
    PersonSearchResponse,
    PostSearchPage,
    PostSearchRequest,
    PostSearchResponse,
    SearchResponse,
    normalise_company,
    normalise_contacts,
    normalise_job,
    normalise_person,
    normalise_post,
)

BASE_URL = "https://api.crustdata.com"
T = TypeVar("T")

# Self-serve list prices from docs.crustdata.com/general/pricing.md.
# Used only for pre-flight estimates; actual spend comes from X-Credits-Used.
SEARCH_BASE_CREDITS = Decimal("0.03")
SEARCH_PREMIUM_GROUP_CREDITS = {
    "taxonomy": Decimal("0.1"),
    "followers": Decimal("0.2"),
    "headcount": Decimal("0.2"),
    "funding": Decimal("0.2"),
    "hiring": Decimal("0.2"),
    "software_reviews": Decimal("0.2"),
    "maps": Decimal("0.2"),
}


def estimate_search_credits(req: CompanySearchRequest) -> Decimal:
    """Upper bound: base + premium groups received + premium groups filtered, per result."""
    received = {f.split(".", 1)[0] for f in req.fields or []}
    per_result = SEARCH_BASE_CREDITS
    per_result += sum(
        (SEARCH_PREMIUM_GROUP_CREDITS.get(g, Decimal(0)) for g in received), Decimal(0)
    )
    per_result += sum(
        (SEARCH_PREMIUM_GROUP_CREDITS.get(g, Decimal(0)) for g in req.filter_groups()), Decimal(0)
    )
    return per_result * req.limit


JOB_CREDITS_PER_RESULT = Decimal("0.03")
# Person search: base 0.03, plus 0.1 for filtering on and 0.1 for receiving `experience`.
PERSON_CREDITS_PER_RESULT = Decimal("0.03") + Decimal("0.1") + Decimal("0.1")


# Contact lookup, per matched person: business email 1 + phone 2. An unmatched person is free.
CONTACT_CREDITS_PER_PERSON = Decimal("3")


def estimate_contact_credits(req: ContactEnrichRequest) -> Decimal:
    return CONTACT_CREDITS_PER_PERSON * len(req.targets)


# Posts are billed per post returned, so the estimate is the most this request can return.
POST_CREDITS_PER_RESULT = Decimal("0.5")


def estimate_post_credits(req: PostSearchRequest) -> Decimal:
    return POST_CREDITS_PER_RESULT * req.limit


def estimate_job_credits(req: JobSearchRequest) -> Decimal:
    return JOB_CREDITS_PER_RESULT * req.limit


def estimate_person_credits(req: PersonSearchRequest) -> Decimal:
    return PERSON_CREDITS_PER_RESULT * req.limit


class ReplayMissing(LookupError):
    """Raised by the replay transport when no recorded response matches a request."""


class CreditBudget:
    def __init__(self, limit: float) -> None:
        self.limit = Decimal(str(limit))
        self.spent = Decimal(0)  # from X-Credits-Used
        self.unconfirmed = Decimal(0)  # estimates for calls that returned no usage header

    @property
    def remaining(self) -> Decimal:
        return self.limit - self.spent - self.unconfirmed

    def preflight(self, estimate: Decimal, endpoint: str) -> None:
        if estimate > self.remaining:
            raise CrustdataError(
                "budget_exceeded",
                f"{endpoint} estimated {estimate} credits; {self.remaining} of {self.limit} remain",
            )

    def record(self, actual: Decimal | None, estimate: Decimal) -> None:
        if actual is not None:
            self.spent += actual
        else:
            self.unconfirmed += estimate


@dataclass
class CallReceipt:
    endpoint: str
    method: str
    mode: Mode
    request_hash: str
    started_at: datetime
    estimated_credits: Decimal
    ok: bool = False
    status_code: int | None = None
    credits_used: Decimal | None = None  # only when the provider reported it
    attempts: int = 0
    latency_ms: int = 0
    cache_hit: bool = False
    rate_limit_remaining: int | None = None
    error_kind: str | None = None
    error_message: str | None = None
    result_count: int | None = None
    replay_source: str | None = None  # provenance label of a replayed fixture


@dataclass(frozen=True)
class ProviderResult(Generic[T]):
    data: T
    receipt: CallReceipt


@dataclass
class _CacheEntry:
    expires: float
    body: Any
    credits_note: Decimal | None = field(default=None)


def request_key(method: str, path: str, body: Any, params: dict[str, str] | None) -> str:
    """Stable hash of a request; shared by the cache and the replay transport."""
    payload = [method.upper(), path, body, params or None]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _decimal(header: str | None) -> Decimal | None:
    if header is None:
        return None
    try:
        return Decimal(header)
    except InvalidOperation:
        return None


class CrustdataClient:
    def __init__(
        self,
        http: httpx.Client,
        api_key: str,
        budget: CreditBudget,
        api_version: str = "2025-11-01",
        mode: Mode = "live",
        max_retries: int = 2,
        cache_ttl_s: float = 3600.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._http = http
        self._headers = {
            "authorization": f"Bearer {api_key}",
            "x-api-version": api_version,
            "content-type": "application/json",
        }
        self.budget = budget
        self.mode = mode
        self._max_retries = max_retries
        self._ttl = cache_ttl_s
        self._sleep = sleep
        self._monotonic = monotonic
        self._clock = clock
        self._cache: dict[str, _CacheEntry] = {}
        self.receipts: list[CallReceipt] = []

    # ---- public, allowlisted operations ----

    def identify_domains(
        self, domains: list[str], exact_match: bool = True
    ) -> ProviderResult[list[IdentifyResult]]:
        if not 1 <= len(domains) <= 25:
            raise ValueError("identify takes 1 to 25 domains")
        body = {"domains": [d.lower() for d in domains], "exact_match": exact_match}
        data, receipt = self._call("POST", "/company/identify", body, None, Decimal(0))
        parsed = self._parse(
            receipt, lambda: TypeAdapter(list[IdentifyResult]).validate_python(data)
        )
        receipt.result_count = sum(len(r.matches) for r in parsed)
        return ProviderResult(parsed, receipt)

    def search_companies(self, req: CompanySearchRequest) -> ProviderResult[CompanySearchPage]:
        data, receipt = self._call(
            "POST", "/company/search", req.to_body(), None, estimate_search_credits(req)
        )
        raw = self._parse(receipt, lambda: SearchResponse.model_validate(data))
        page = CompanySearchPage(
            companies=[
                normalise_company(c, receipt.started_at, "/company/search") for c in raw.companies
            ],
            next_cursor=raw.next_cursor,
            total_count=raw.total_count,
        )
        receipt.result_count = len(page.companies)
        return ProviderResult(page, receipt)

    def search_jobs(self, req: JobSearchRequest) -> ProviderResult[JobSearchPage]:
        data, receipt = self._call(
            "POST", "/job/search", req.to_body(), None, estimate_job_credits(req)
        )
        raw = self._parse(receipt, lambda: JobSearchResponse.model_validate(data))
        page = JobSearchPage(
            postings=[normalise_job(j, receipt.started_at) for j in raw.job_listings],
            next_cursor=raw.next_cursor,
            total_count=raw.total_count,
        )
        receipt.result_count = len(page.postings)
        return ProviderResult(page, receipt)

    def search_people(self, req: PersonSearchRequest) -> ProviderResult[PersonSearchPage]:
        data, receipt = self._call(
            "POST", "/person/search", req.to_body(), None, estimate_person_credits(req)
        )
        raw = self._parse(receipt, lambda: PersonSearchResponse.model_validate(data))
        page = PersonSearchPage(
            people=[normalise_person(p, receipt.started_at) for p in raw.profiles],
            next_cursor=raw.next_cursor,
            total_count=raw.total_count,
        )
        receipt.result_count = len(page.people)
        return ProviderResult(page, receipt)

    def enrich_contacts(
        self, req: ContactEnrichRequest
    ) -> ProviderResult[dict[int, list[ContactPoint]]]:
        """Email and phone for the people asked about, by our person id. Paid per matched person."""
        data, receipt = self._call(
            "POST", "/person/contact/enrich", req.to_body(), None, estimate_contact_credits(req)
        )
        raw = self._parse(receipt, lambda: ContactEnrichResponse.model_validate(data))
        found = normalise_contacts(req, raw)
        receipt.result_count = len(found)
        return ProviderResult(found, receipt)

    def search_posts(self, req: PostSearchRequest) -> ProviderResult[PostSearchPage]:
        data, receipt = self._call(
            "POST", "/social_post/search", req.to_body(), None, estimate_post_credits(req)
        )
        raw = self._parse(receipt, lambda: PostSearchResponse.model_validate(data))
        page = PostSearchPage(
            posts=[normalise_post(p, receipt.started_at) for p in raw.posts],
            next_cursor=raw.next_cursor,
            total_count=raw.total_count,
        )
        receipt.result_count = len(page.posts)
        return ProviderResult(page, receipt)

    def endpoint_access(
        self, path: str | None = None, category: str | None = None
    ) -> ProviderResult[EndpointAccess]:
        params = {k: v for k, v in (("path", path), ("category", category)) if v}
        data, receipt = self._call("GET", "/account/endpoints", None, params, Decimal(0))
        return ProviderResult(
            self._parse(receipt, lambda: EndpointAccess.model_validate(data)), receipt
        )

    # ---- transport ----

    def _parse(self, receipt: CallReceipt, fn: Callable[[], T]) -> T:
        try:
            return fn()
        except ValidationError as exc:
            receipt.ok = False
            receipt.error_kind = "malformed_response"
            receipt.error_message = str(exc.errors()[0]["msg"])
            raise CrustdataError(
                "malformed_response", "response did not match the documented schema"
            ) from exc

    def _call(
        self, method: str, path: str, body: Any, params: dict[str, str] | None, estimate: Decimal
    ) -> tuple[Any, CallReceipt]:
        key = request_key(method, path, body, params)
        receipt = CallReceipt(
            endpoint=path,
            method=method,
            mode=self.mode,
            request_hash=key,
            started_at=self._clock(),
            estimated_credits=estimate,
        )
        self.receipts.append(receipt)
        cached = self._cache.get(key)
        if cached and cached.expires > self._monotonic():
            receipt.ok, receipt.cache_hit, receipt.credits_used = True, True, Decimal(0)
            return cached.body, receipt
        try:
            self.budget.preflight(estimate, path)
        except CrustdataError as exc:
            receipt.error_kind, receipt.error_message = exc.kind, str(exc)
            raise
        started = time.perf_counter()
        try:
            data, resp = self._send_with_retries(method, path, body, params, receipt)
        except CrustdataError as exc:
            receipt.error_kind, receipt.error_message = exc.kind, str(exc)
            receipt.latency_ms = int((time.perf_counter() - started) * 1000)
            self.budget.record(receipt.credits_used, Decimal(0))
            raise
        receipt.latency_ms = int((time.perf_counter() - started) * 1000)
        receipt.ok, receipt.status_code = True, resp.status_code
        receipt.replay_source = resp.headers.get("x-trigger_point-replay-source")
        receipt.credits_used = _decimal(resp.headers.get("x-credits-used"))
        remaining = resp.headers.get("x-ratelimit-remaining")
        receipt.rate_limit_remaining = int(remaining) if remaining and remaining.isdigit() else None
        self.budget.record(receipt.credits_used, estimate)
        self._cache[key] = _CacheEntry(self._monotonic() + self._ttl, data)
        return data, receipt

    def _send_with_retries(
        self,
        method: str,
        path: str,
        body: Any,
        params: dict[str, str] | None,
        receipt: CallReceipt,
    ) -> tuple[Any, httpx.Response]:
        last: CrustdataError | None = None
        for attempt in range(self._max_retries + 1):
            receipt.attempts = attempt + 1
            try:
                resp = self._http.request(
                    method, BASE_URL + path, json=body, params=params, headers=self._headers
                )
            except ReplayMissing as exc:
                raise CrustdataError("replay_missing", str(exc)) from exc
            except httpx.TimeoutException:
                last = CrustdataError("timeout", f"{path} timed out")
            except httpx.HTTPError as exc:
                last = CrustdataError("network", type(exc).__name__)
            else:
                receipt.status_code = resp.status_code
                if resp.status_code == 200:
                    try:
                        return resp.json(), resp
                    except json.JSONDecodeError as exc:
                        raise CrustdataError("malformed_response", "non-JSON body") from exc
                try:
                    payload: Any = resp.json()
                except json.JSONDecodeError:
                    payload = None
                if resp.status_code == 429:
                    last = CrustdataError("rate_limited", "rate limited", status=429)
                    if attempt < self._max_retries:
                        reset = resp.headers.get("x-ratelimit-reset", "1")
                        wait = min(float(reset) if reset.replace(".", "").isdigit() else 1.0, 60.0)
                        self._sleep(wait + random.uniform(0, 1))  # noqa: S311
                    continue
                err = error_from_response(resp.status_code, payload)
                receipt.credits_used = _decimal(resp.headers.get("x-credits-used"))
                if not err.retryable:
                    raise err
                last = err
            if attempt < self._max_retries:
                self._sleep(min(2.0**attempt, 10.0) + random.uniform(0, 0.5))  # noqa: S311
        assert last is not None
        raise last
