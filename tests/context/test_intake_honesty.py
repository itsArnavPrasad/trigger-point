"""An intake must say what it could not read, and an empty profile can never be approved."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.conftest import FIXTURES
from trigger_point.context.extractor import ExtractionResult, LlmContextExtractor
from trigger_point.context.service import (
    MAX_EXTRACTION_TRIES,
    ContextService,
    EmptyProfile,
    IntakeBrief,
    IntakeFailed,
    assess_readability,
)
from trigger_point.llm.replay import ReplayStructuredLlm
from trigger_point.models.context import ContextDraft
from trigger_point.store.db import Store
from trigger_point.web.crawl import PageRecord
from trigger_point.web.fetcher import FixtureFetcher

MODES = {"web": "replay", "llm": "replay"}
NOW = datetime(2026, 10, 31, tzinfo=UTC)


def service(tmp_path: Path) -> ContextService:
    extractor = LlmContextExtractor(ReplayStructuredLlm(FIXTURES / "llm"))
    return ContextService(
        FixtureFetcher(FIXTURES / "sites"),
        extractor,
        Store(tmp_path / "c.db"),
        MODES,  # type: ignore[arg-type]
    )


def page(text: str, status: str = "ok") -> PageRecord:
    return PageRecord("u", "u", status, NOW, 200, None, text, None, None)  # type: ignore[arg-type]


def test_a_loading_screen_is_thin_not_ok() -> None:
    assert assess_readability([page("Loading..."), page("Please wait")]) == "thin"


def test_real_text_is_ok() -> None:
    assert assess_readability([page("We help support teams. " * 40)]) == "ok"


def test_nothing_fetched_is_none() -> None:
    assert assess_readability([page("", "http_error")]) == "none"


def test_empty_profile_cannot_be_approved(tmp_path: Path) -> None:
    svc = service(tmp_path)
    out = svc.intake("unknown-site.example", "Find customers")
    with pytest.raises(EmptyProfile):
        svc.approve(out.context_id, "user", acknowledge_unsupported=True)


def test_fixture_mode_names_the_real_reason(tmp_path: Path) -> None:
    out = service(tmp_path).intake("unknown-site.example", "Find customers")
    assert out.context.readability == "none"
    assert any("no fixture" in u.lower() for u in out.context.unknowns)


def test_a_product_note_is_a_user_statement_that_makes_the_profile_usable(tmp_path: Path) -> None:
    svc = service(tmp_path)
    brief = IntakeBrief(
        product_note="Tulip is an AI tutor for CBSE students.",
        target_geography="Mumbai",
        time_horizon="90 days",
    )
    out = svc.intake("unknown-site.example", "Find customers", brief=brief)
    claim = out.context.product_summary[0]
    assert claim.kind == "user_provided" and "AI tutor" in claim.text
    assert out.context.target_geography == "Mumbai" and out.context.time_horizon == "90 days"
    assert svc.approve(out.context_id, "user").status == "approved"


def test_thin_sites_are_described_without_guessing_the_cause(tmp_path: Path) -> None:
    from trigger_point.context.service import _apply_brief

    ctx = service(tmp_path).intake("supportpilot.example", "Find customers").context
    thin = _apply_brief(ctx, IntakeBrief(), "thin")
    assert thin.unknowns[0].startswith("The site returned almost no readable text")
    assert "JavaScript" not in thin.unknowns[0]


class FlakyExtractor:
    """A model that answers with nothing a few times, then answers properly."""

    def __init__(self, inner: LlmContextExtractor, empties: int) -> None:
        self.inner, self.empties, self.calls = inner, empties, 0

    def extract(self, seed_url: str, goal: str, pages: list[PageRecord]) -> ExtractionResult:
        self.calls += 1
        if self.calls <= self.empties:
            return ExtractionResult(ContextDraft(), None, "live")
        return self.inner.extract(seed_url, goal, pages)


def flaky(tmp_path: Path, empties: int) -> tuple[ContextService, FlakyExtractor]:
    extractor = FlakyExtractor(LlmContextExtractor(ReplayStructuredLlm(FIXTURES / "llm")), empties)
    svc = ContextService(
        FixtureFetcher(FIXTURES / "sites"),
        extractor,
        Store(tmp_path / "f.db"),
        MODES,  # type: ignore[arg-type]
    )
    return svc, extractor


def test_an_empty_model_answer_on_a_readable_site_is_retried(tmp_path: Path) -> None:
    svc, extractor = flaky(tmp_path, 1)
    out = svc.intake("supportpilot.example", "Find customers")
    assert extractor.calls == 2 and out.context.has_usable_facts()


def test_a_model_that_stays_empty_fails_loudly(tmp_path: Path) -> None:
    svc, extractor = flaky(tmp_path, 99)
    with pytest.raises(IntakeFailed, match="no facts"):
        svc.intake("supportpilot.example", "Find customers")
    assert extractor.calls == MAX_EXTRACTION_TRIES
