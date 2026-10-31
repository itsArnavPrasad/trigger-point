from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from trigger_point.api.app import AppDeps, create_app
from trigger_point.config import load_settings
from trigger_point.context.extractor import ContextExtractor, LlmContextExtractor
from trigger_point.llm.replay import ReplayStructuredLlm
from trigger_point.store.db import Store
from trigger_point.web.fetcher import Fetcher, FixtureFetcher

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "replay"
assert (FIXTURES / "sites").is_dir(), FIXTURES

MakeClient = Callable[..., tuple[TestClient, Store]]


@pytest.fixture
def make_client(tmp_path: Path) -> MakeClient:
    def _make(
        fetcher: Fetcher | None = None,
        extractor: ContextExtractor | None = None,
        env: dict[str, str] | None = None,
    ) -> tuple[TestClient, Store]:
        settings = load_settings(env or {})
        store = Store(tmp_path / "test.db")
        deps = AppDeps(
            fetcher=fetcher or FixtureFetcher(FIXTURES / "sites"),
            extractor=extractor or LlmContextExtractor(ReplayStructuredLlm(FIXTURES / "llm")),
            store=store,
        )
        return TestClient(create_app(settings, deps)), store

    return _make


LIVE_ENV = {
    "WEB_MODE": "live",
    "LLM_MODE": "live",
    "CRUSTDATA_MODE": "live",
    "CRUSTDATA_API_KEY": "x",
    "HYDE_INFERENCE_API_KEY": "y",
}
