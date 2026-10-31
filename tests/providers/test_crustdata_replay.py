import json
from pathlib import Path

import httpx
import pytest

from tests.providers.crustdata_payloads import CASHFREE
from trigger_point.providers.crustdata.client import CreditBudget, CrustdataClient
from trigger_point.providers.crustdata.errors import CrustdataError
from trigger_point.providers.crustdata.replay import RecordingTransport, ReplayTransport


def test_record_then_replay_runs_the_same_client_code(tmp_path: Path) -> None:
    live = httpx.MockTransport(
        lambda r: httpx.Response(200, json=CASHFREE, headers={"x-credits-used": "0"})
    )
    recorder = CrustdataClient(
        httpx.Client(transport=RecordingTransport(live, tmp_path)),
        api_key="k",
        budget=CreditBudget(1),
    )
    recorder.identify_domains(["cashfree.com"])
    [fixture] = list((tmp_path / "company_identify").glob("*.json"))
    saved = json.loads(fixture.read_text())
    assert saved["_source"].startswith("recorded live")
    assert "authorization" not in json.dumps(saved).lower()

    replay = CrustdataClient(
        httpx.Client(transport=ReplayTransport(tmp_path)),
        api_key="k",
        budget=CreditBudget(1),
        mode="replay",
    )
    result = replay.identify_domains(["cashfree.com"])
    assert len(result.data[0].matches) == 3
    assert result.receipt.mode == "replay" and result.receipt.credits_used == 0


def test_replay_without_matching_fixture_is_a_typed_error(tmp_path: Path) -> None:
    client = CrustdataClient(
        httpx.Client(transport=ReplayTransport(tmp_path)),
        api_key="k",
        budget=CreditBudget(1),
        mode="replay",
    )
    with pytest.raises(CrustdataError) as e:
        client.identify_domains(["unknown.example"])
    assert e.value.kind == "replay_missing"
    assert "company_identify/" in str(e.value)
