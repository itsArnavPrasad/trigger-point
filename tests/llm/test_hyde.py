import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from trigger_point.llm.base import LlmError, LlmRequest
from trigger_point.llm.hyde import HydeStructuredLlm


class Answer(BaseModel):
    city: str
    population: int


REQ = LlmRequest(task="t", replay_key="k", system="sys", user="usr", schema=Answer)


def completion(content: str | None, finish: str = "stop", **msg: Any) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-1",
            "model": "hyde/glm-5.3-flash",
            "choices": [
                {
                    "finish_reason": finish,
                    "message": {"role": "assistant", "content": content, **msg},
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 50,
                "completion_tokens_details": {"reasoning_tokens": 40},
            },
        },
    )


def make(handler: Any, **kw: Any) -> tuple[HydeStructuredLlm, list[float]]:
    sleeps: list[float] = []
    llm = HydeStructuredLlm(
        httpx.Client(transport=httpx.MockTransport(handler)),
        base_url="https://inference.hyde.tech/v1",
        api_key="sk-test",
        model="hyde/glm-5.3-flash",
        sleep=sleeps.append,
        **kw,
    )
    return llm, sleeps


def test_success_sends_strict_json_schema_and_parses_usage() -> None:
    seen: list[httpx.Request] = []

    def handler(r: httpx.Request) -> httpx.Response:
        seen.append(r)
        return completion('{"city": "Paris", "population": 2100000}')

    llm, _ = make(handler)
    res = llm.complete(REQ)
    assert res.output == Answer(city="Paris", population=2100000)
    assert res.mode == "live"
    assert res.usage is not None
    assert (res.usage.input_tokens, res.usage.output_tokens, res.usage.reasoning_tokens) == (
        10,
        50,
        40,
    )
    body = json.loads(seen[0].content)
    assert seen[0].url == "https://inference.hyde.tech/v1/chat/completions"
    assert seen[0].headers["authorization"] == "Bearer sk-test"
    assert body["model"] == "hyde/glm-5.3-flash" and body["max_tokens"] == 16000
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert [m["role"] for m in body["messages"]] == ["system", "user"]


def test_json_inside_markdown_fence_is_accepted() -> None:
    llm, _ = make(lambda r: completion('```json\n{"city": "Oslo", "population": 1}\n```'))
    assert llm.complete(REQ).output.city == "Oslo"


def test_length_finish_is_truncated_error() -> None:
    llm, _ = make(lambda r: completion(None, finish="length"))
    with pytest.raises(LlmError) as e:
        llm.complete(REQ)
    assert e.value.kind == "truncated"


def test_schema_mismatch_is_invalid_output() -> None:
    llm, _ = make(lambda r: completion('{"city": "Paris"}'))
    with pytest.raises(LlmError) as e:
        llm.complete(REQ)
    assert e.value.kind == "invalid_output"


def test_refusal_is_reported() -> None:
    llm, _ = make(lambda r: completion(None, refusal="I can't help with that"))
    with pytest.raises(LlmError) as e:
        llm.complete(REQ)
    assert e.value.kind == "refusal"


def test_auth_error_is_terminal_and_not_retried() -> None:
    calls: list[int] = []

    def handler(r: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(401, json={"error": {"message": "Invalid API key"}})

    llm, sleeps = make(handler)
    with pytest.raises(LlmError) as e:
        llm.complete(REQ)
    assert e.value.kind == "auth" and len(calls) == 1 and sleeps == []
    assert "sk-test" not in str(e.value)


def test_model_access_403_is_auth() -> None:
    llm, _ = make(lambda r: httpx.Response(403, json={"error": {"message": "key not allowed"}}))
    with pytest.raises(LlmError) as e:
        llm.complete(REQ)
    assert e.value.kind == "auth"


def test_rate_limit_then_success_retries_with_backoff() -> None:
    responses = [httpx.Response(429, json={}), completion('{"city": "Rome", "population": 3}')]
    llm, sleeps = make(lambda r: responses.pop(0))
    assert llm.complete(REQ).output.city == "Rome"
    assert len(sleeps) == 1 and sleeps[0] > 0


def test_server_errors_exhaust_retries() -> None:
    calls: list[int] = []

    def handler(r: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503, json={})

    llm, sleeps = make(handler, max_retries=2)
    with pytest.raises(LlmError) as e:
        llm.complete(REQ)
    assert e.value.kind == "server" and len(calls) == 3 and len(sleeps) == 2


def test_timeout_is_retried_then_reported() -> None:
    def handler(r: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=r)

    llm, _ = make(handler, max_retries=1)
    with pytest.raises(LlmError) as e:
        llm.complete(REQ)
    assert e.value.kind == "timeout"
