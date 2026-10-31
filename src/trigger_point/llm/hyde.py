"""Hyde inference gateway (OpenAI chat-completions format) with strict JSON-schema output."""

from __future__ import annotations

import json
import random
import re
import time
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import ValidationError

from trigger_point.config import Mode
from trigger_point.llm.base import LlmError, LlmRequest, LlmResponse, LlmUsage, T

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def default_llm_http_client() -> httpx.Client:
    # GLM reasons before answering; long reads are normal.
    return httpx.Client(timeout=httpx.Timeout(300.0, connect=10.0), trust_env=False)


class HydeStructuredLlm:
    def __init__(
        self,
        http: httpx.Client,
        base_url: str,
        api_key: str,
        model: str,
        max_retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = http
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._key = api_key
        self._model = model
        self._max_retries = max_retries
        self._sleep = sleep

    @property
    def mode(self) -> Mode:
        return "live"

    def complete(self, req: LlmRequest[T]) -> LlmResponse[T]:
        body = {
            "model": self._model,
            "max_tokens": req.max_tokens,
            "messages": [
                {"role": "system", "content": req.system},
                {"role": "user", "content": req.user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": req.task,
                    "schema": req.schema.model_json_schema(),
                    "strict": True,
                },
            },
        }
        started = time.perf_counter()
        data = self._post_with_retries(body)
        latency_ms = int((time.perf_counter() - started) * 1000)
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        if message.get("refusal") or (message.get("provider_specific_fields") or {}).get("refusal"):
            raise LlmError("refusal", "model declined the request")
        if choice.get("finish_reason") == "length":
            raise LlmError("truncated", "max_tokens reached before an answer (reasoning model)")
        content = (message.get("content") or "").strip()
        fenced = _FENCE.match(content)
        if fenced:
            content = fenced.group(1)
        try:
            output = req.schema.model_validate_json(content)
        except ValidationError as exc:
            raise LlmError(
                "invalid_output",
                f"response does not match {req.task} schema: {exc.errors()[0]['msg']}",
            ) from exc
        usage = data.get("usage") or {}
        details = usage.get("completion_tokens_details") or {}
        return LlmResponse(
            output=output,
            usage=LlmUsage(
                provider="hyde",
                model=str(data.get("model") or self._model),
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
                reasoning_tokens=details.get("reasoning_tokens"),
                request_id=data.get("id"),
                latency_ms=latency_ms,
            ),
            mode="live",
        )

    def _post_with_retries(self, body: dict[str, Any]) -> dict[str, Any]:
        last: LlmError | None = None
        for attempt in range(self._max_retries + 1):
            if attempt:
                self._sleep(min(2.0**attempt, 20.0) + random.uniform(0, 1))  # noqa: S311
            try:
                resp = self._http.post(
                    self._url, json=body, headers={"authorization": f"Bearer {self._key}"}
                )
            except httpx.TimeoutException:
                last = LlmError("timeout", "Hyde request timed out")
                continue
            except httpx.HTTPError as exc:
                last = LlmError("network", type(exc).__name__)
                continue
            if resp.status_code in (401, 403):
                raise LlmError(
                    "auth",
                    f"Hyde rejected the key or model (HTTP {resp.status_code}); "
                    "check HYDE_INFERENCE_API_KEY and LLM_MODEL",
                )
            if resp.status_code == 429:
                last = LlmError("rate_limited", "Hyde rate limit")
                continue
            if resp.status_code >= 500:
                last = LlmError("server", f"Hyde HTTP {resp.status_code}")
                continue
            if resp.status_code >= 400:
                raise LlmError(
                    "invalid_output", f"Hyde rejected the request (HTTP {resp.status_code})"
                )
            try:
                data: dict[str, Any] = resp.json()
            except json.JSONDecodeError as exc:
                raise LlmError("invalid_output", "Hyde returned non-JSON") from exc
            return data
        assert last is not None
        raise last
