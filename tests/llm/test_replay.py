import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from trigger_point.llm.base import LlmError, LlmRequest
from trigger_point.llm.replay import ReplayStructuredLlm


class Answer(BaseModel):
    city: str


def req(key: str) -> LlmRequest[Answer]:
    return LlmRequest(task="geo", replay_key=key, system="s", user="u", schema=Answer)


def test_replay_loads_fixture_and_ignores_annotations(tmp_path: Path) -> None:
    (tmp_path / "geo").mkdir()
    (tmp_path / "geo" / "paris.json").write_text(json.dumps({"_source": "hand", "city": "Paris"}))
    res = ReplayStructuredLlm(tmp_path).complete(req("paris"))
    assert res.output.city == "Paris" and res.mode == "replay" and res.usage is None


def test_replay_missing_fixture_is_typed_error(tmp_path: Path) -> None:
    with pytest.raises(LlmError) as e:
        ReplayStructuredLlm(tmp_path).complete(req("nope"))
    assert e.value.kind == "replay_missing"


def test_replay_key_cannot_escape_root(tmp_path: Path) -> None:
    with pytest.raises(LlmError) as e:
        ReplayStructuredLlm(tmp_path / "root").complete(req("../../etc/passwd"))
    assert e.value.kind == "replay_missing"


def test_replay_invalid_fixture(tmp_path: Path) -> None:
    (tmp_path / "geo").mkdir()
    (tmp_path / "geo" / "x.json").write_text("{}")
    with pytest.raises(LlmError) as e:
        ReplayStructuredLlm(tmp_path).complete(req("x"))
    assert e.value.kind == "invalid_output"
