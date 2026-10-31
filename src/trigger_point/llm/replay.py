"""Replay LLM: returns recorded or hand-authored outputs from `root/<task>/<replay_key>.json`."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import ValidationError

from trigger_point.config import Mode
from trigger_point.llm.base import LlmError, LlmRequest, LlmResponse, T

_SAFE_KEY = re.compile(r"^[A-Za-z0-9._-]+$")


class ReplayStructuredLlm:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    @property
    def mode(self) -> Mode:
        return "replay"

    def complete(self, req: LlmRequest[T]) -> LlmResponse[T]:
        if (
            not _SAFE_KEY.match(req.task)
            or not _SAFE_KEY.match(req.replay_key)
            or ".." in (req.task + req.replay_key)
        ):
            raise LlmError("replay_missing", f"unsafe replay key {req.task}/{req.replay_key}")
        path = self._root / req.task / f"{req.replay_key}.json"
        if not path.is_file():
            raise LlmError("replay_missing", f"no replay fixture {req.task}/{req.replay_key}.json")
        try:
            raw = json.loads(path.read_text())
            output = req.schema.model_validate(
                {k: v for k, v in raw.items() if not k.startswith("_")}
            )
        except (ValidationError, json.JSONDecodeError) as exc:
            raise LlmError("invalid_output", f"replay fixture {path.name} is invalid") from exc
        return LlmResponse(output=output, usage=None, mode="replay")
