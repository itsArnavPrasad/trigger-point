import json
from decimal import Decimal
from typing import Any

import httpx
import pytest

from tests.providers.crustdata_payloads import CASHFREE, NO_MATCH, SEARCH_PAGE
from trigger_point.providers.crustdata.client import CreditBudget, CrustdataClient
from trigger_point.providers.crustdata.errors import CrustdataError
from trigger_point.providers.crustdata.models import (
    CompanySearchRequest,
    Condition,
    ConditionGroup,
    SemanticSearch,
)


def resp(status: int, body: Any, **headers: str) -> httpx.Response:
    return httpx.Response(status, json=body, headers=headers)


def make(handler: Any, budget: float = 5.0, **kw: Any) -> tuple[CrustdataClient, list[float]]:
    sleeps: list[float] = []
    client = CrustdataClient(
        httpx.Client(transport=httpx.MockTransport(handler)),
        api_key="cd-key",
        budget=CreditBudget(budget),
        sleep=sleeps.append,
        **kw,
    )
    return client, sleeps


def search_req(limit: int = 2) -> CompanySearchRequest:
    return CompanySearchRequest(
        search=SemanticSearch(query="B2B SaaS companies scaling customer support"),
        filters=ConditionGroup(
            op="and",
            conditions=[
                Condition(field="locations.country", type="=", value="USA"),
                Condition(field="headcount.total", type="=>", value=50),
            ],
        ),
        fields=["basic_info", "headcount", "hiring"],
        limit=limit,
    )


def test_identify_sends_documented_headers_and_body() -> None:
    seen: list[httpx.Request] = []

    def handler(r: httpx.Request) -> httpx.Response:
        seen.append(r)
        return resp(200, CASHFREE, **{"x-credits-used": "0"})

    client, _ = make(handler)
    result = client.identify_domains(["cashfree.com"])
    assert len(result.data[0].matches) == 3
    req = seen[0]
    assert str(req.url) == "https://api.crustdata.com/company/identify"
    assert req.headers["authorization"] == "Bearer cd-key"
    assert req.headers["x-api-version"] == "2025-11-01"
    assert json.loads(req.content) == {"domains": ["cashfree.com"], "exact_match": True}
    assert result.receipt.credits_used == Decimal("0")
    assert result.receipt.endpoint == "/company/identify"


def test_empty_identify_is_a_result_not_an_error() -> None:
    client, _ = make(lambda r: resp(200, NO_MATCH))
    result = client.identify_domains(["thisdomaindoesnotexist12345xyz.com"])
    assert result.data[0].matches == []
    assert result.receipt.ok


def test_search_parses_normalises_and_records_actual_credits() -> None:
    client, _ = make(
        lambda r: resp(
            200, SEARCH_PAGE, **{"x-credits-used": "0.86", "x-ratelimit-remaining": "28"}
        )
    )
    result = client.search_companies(search_req())
    assert [c.name for c in result.data.companies] == ["Ledgerloop", "Quartzdesk"]
    assert result.data.companies[0].headcount_growth_6m_pct == 9.5
    assert result.data.companies[0].hiring_openings == 14
    assert result.receipt.credits_used == Decimal("0.86")
    assert result.receipt.estimated_credits > 0
    assert client.budget.spent == Decimal("0.86")


def test_search_request_serialises_documented_filter_grammar() -> None:
    body = search_req().to_body()
    assert body["filters"]["conditions"][1] == {
        "field": "headcount.total",
        "type": "=>",
        "value": 50,
    }
    assert body["search"] == {
        "query": "B2B SaaS companies scaling customer support",
        "mode": "hybrid",
    }
    assert "sorts" not in body and "cursor" not in body


def test_unknown_filter_field_is_rejected_before_any_request() -> None:
    with pytest.raises(ValueError, match="not a supported"):
        Condition(field="basic_info.ceo_email", type="=", value="x")


def test_in_operator_requires_list_and_null_ops_require_none() -> None:
    with pytest.raises(ValueError):
        Condition(field="locations.country", type="in", value="USA")
    with pytest.raises(ValueError):
        Condition(field="funding.last_round_type", type="is_null", value="x")
    Condition(field="funding.last_round_type", type="is_null", value=None)


def test_ranked_search_limit_and_sorts_are_validated() -> None:
    with pytest.raises(ValueError, match="100"):
        CompanySearchRequest(search=SemanticSearch(query="x"), limit=101)
    with pytest.raises(ValueError, match="filters or search"):
        CompanySearchRequest(limit=5)


def test_budget_fails_closed_before_the_request() -> None:
    calls: list[int] = []

    def handler(r: httpx.Request) -> httpx.Response:
        calls.append(1)
        return resp(200, SEARCH_PAGE)

    client, _ = make(handler, budget=0.5)
    with pytest.raises(CrustdataError) as e:
        client.search_companies(search_req(limit=100))
    assert e.value.kind == "budget_exceeded" and calls == []


@pytest.mark.parametrize(
    ("status", "body", "kind", "retryable"),
    [
        (
            400,
            {"error": {"type": "invalid_request", "message": "bad", "metadata": []}},
            "invalid_request",
            False,
        ),
        (401, {"message": "Invalid API key in request"}, "auth", False),
        (
            402,
            {
                "error": {
                    "type": "insufficient_credits",
                    "message": "Insufficient credits.",
                    "metadata": [],
                }
            },
            "insufficient_credits",
            False,
        ),
        (
            403,
            {
                "error": {
                    "type": "permission_error",
                    "message": "You do not have permission",
                    "metadata": [],
                }
            },
            "permission",
            False,
        ),
        (404, {"error": "Not Found", "description": "Company not found."}, "not_found", False),
    ],
)
def test_terminal_errors_are_typed_and_not_retried(
    status: int, body: Any, kind: str, retryable: bool
) -> None:
    calls: list[int] = []

    def handler(r: httpx.Request) -> httpx.Response:
        calls.append(1)
        return resp(status, body)

    client, sleeps = make(handler)
    with pytest.raises(CrustdataError) as e:
        client.identify_domains(["a.com"])
    assert e.value.kind == kind and e.value.retryable is retryable
    assert len(calls) == 1 and sleeps == []
    assert "cd-key" not in str(e.value)
    assert client.receipts[-1].ok is False and client.receipts[-1].error_kind == kind


def test_denied_fields_are_surfaced() -> None:
    body = {
        "error": {
            "type": "permission_error",
            "message": "Access denied to fields: hiring",
            "metadata": [
                {"denied_fields": ["hiring"], "permitted_fields": ["basic_info", "headcount"]}
            ],
        }
    }
    client, _ = make(lambda r: resp(403, body))
    with pytest.raises(CrustdataError) as e:
        client.search_companies(search_req())
    assert e.value.kind == "fields_denied" and e.value.denied_fields == ["hiring"]


def test_rate_limit_waits_for_reset_then_succeeds() -> None:
    responses = [resp(429, {}, **{"x-ratelimit-reset": "3"}), resp(200, CASHFREE)]
    client, sleeps = make(lambda r: responses.pop(0))
    client.identify_domains(["cashfree.com"])
    assert len(sleeps) == 1 and 3 <= sleeps[0] < 4
    assert client.receipts[-1].attempts == 2


def test_server_errors_exhaust_retries_then_fail() -> None:
    client, sleeps = make(lambda r: resp(503, {}), max_retries=2)
    with pytest.raises(CrustdataError) as e:
        client.identify_domains(["a.com"])
    assert e.value.kind == "server" and len(sleeps) == 2


def test_timeout_is_typed() -> None:
    def handler(r: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=r)

    client, _ = make(handler, max_retries=0)
    with pytest.raises(CrustdataError) as e:
        client.identify_domains(["a.com"])
    assert e.value.kind == "timeout"


def test_malformed_response_is_typed() -> None:
    client, _ = make(lambda r: resp(200, {"unexpected": True}))
    with pytest.raises(CrustdataError) as e:
        client.identify_domains(["a.com"])
    assert e.value.kind == "malformed_response"


def test_identical_reads_are_cached() -> None:
    calls: list[int] = []

    def handler(r: httpx.Request) -> httpx.Response:
        calls.append(1)
        return resp(200, CASHFREE, **{"x-credits-used": "0"})

    client, _ = make(handler)
    client.identify_domains(["cashfree.com"])
    second = client.identify_domains(["cashfree.com"])
    assert len(calls) == 1 and second.receipt.cache_hit is True


def test_endpoint_access_probe() -> None:
    body = {
        "api_version": "2025-11-01",
        "token_limit_rpm": None,
        "endpoints": [
            {
                "path": "/company/search",
                "category": "Company",
                "status": "enabled",
                "effective_rate_limit_rpm": 30,
                "fields": {"enabled": [], "disabled": []},
                "base_credits": 0.03,
            },
            {
                "path": "/company/enrich",
                "category": "Company",
                "status": "disabled",
                "effective_rate_limit_rpm": 15,
                "fields": {"enabled": [], "disabled": []},
                "base_credits": 2,
            },
        ],
    }
    seen: list[httpx.Request] = []

    def handler(r: httpx.Request) -> httpx.Response:
        seen.append(r)
        return resp(200, body)

    client, _ = make(handler)
    access = client.endpoint_access(category="Company").data
    assert seen[0].method == "GET" and seen[0].url.params["category"] == "Company"
    assert access.is_enabled("/company/search") and not access.is_enabled("/company/enrich")
    assert not access.is_enabled("/job/search")  # unknown means not enabled
