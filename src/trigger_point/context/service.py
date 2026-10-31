"""Website → BusinessContext intake, plus human edit/approve. Each change is a new version."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import ValidationError

from trigger_point.context.extractor import ContextExtractor
from trigger_point.context.grounding import ground_context, normalize_for_match
from trigger_point.models.context import (
    CLAIM_LIST_FIELDS,
    BusinessContext,
    ContextClaim,
    ContextDraft,
    Mode,
    PageRef,
    Readability,
    RunMode,
)
from trigger_point.models.run import LlmUsageRecord, PageFailure, RunReceipt
from trigger_point.security.url_guard import check_url_static, normalize_seed_url
from trigger_point.store.db import Store
from trigger_point.web.crawl import PageRecord, crawl_site
from trigger_point.web.fetcher import Fetcher

MAX_EXTRACTION_TRIES = 3
MIN_READABLE_CHARS = 400  # below this a site said almost nothing, whatever the HTTP status was
EDITABLE_FIELDS = frozenset(CLAIM_LIST_FIELDS) | {"company_name", "unknowns"}


class IntakeFailed(RuntimeError):
    def __init__(self, message: str, run_id: str) -> None:
        super().__init__(message)
        self.run_id = run_id


class ContextNotFound(LookupError):
    pass


class UnsupportedFactsRemain(RuntimeError):
    def __init__(self, texts: list[str]) -> None:
        super().__init__(f"{len(texts)} unsupported facts remain")
        self.texts = texts


class InvalidEdit(ValueError):
    pass


class VersionMismatch(RuntimeError):
    def __init__(self, expected: int, current: int) -> None:
        super().__init__(f"expected v{expected}, current is v{current}")
        self.expected = expected
        self.current = current


class EmptyProfile(RuntimeError):
    """Nothing in the profile is sourced or user-provided, so there is nothing to approve."""


@dataclass(frozen=True)
class IntakeBrief:
    """What the user says up front. These are user statements, never treated as sourced facts."""

    product_note: str | None = None
    target_geography: str | None = None
    time_horizon: str | None = None


@dataclass(frozen=True)
class IntakeOutcome:
    context_id: str
    run_id: str
    context: BusinessContext


def _now() -> datetime:
    return datetime.now(UTC)


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _has_claims(draft: ContextDraft) -> bool:
    return draft.company_name is not None or any(getattr(draft, f) for f in CLAIM_LIST_FIELDS)


def assess_readability(pages: list[PageRecord]) -> Readability:
    """`thin` is a page that answered with almost nothing, typically a JavaScript app's shell."""
    text = sum(len(p.text or "") for p in pages if p.fetch_status == "ok")
    if text == 0:
        return "none"
    return "thin" if text < MIN_READABLE_CHARS else "ok"


def combine_modes(modes: dict[str, Mode]) -> RunMode:
    """A run is live only if every provider it used was live."""
    used = set(modes.values())
    if used == {"live"}:
        return "live"
    return "replay" if used == {"replay"} else "mixed"


def _page_ref(p: PageRecord) -> PageRef:
    return PageRef(
        url=p.url,
        final_url=p.final_url,
        title=p.title,
        fetch_status=p.fetch_status,
        retrieved_at=p.retrieved_at,
        text_sha256=p.raw_sha256,
        http_status=p.http_status,
        error=p.error,
    )


def _apply_brief(
    context: BusinessContext, brief: IntakeBrief, readability: Readability
) -> BusinessContext:
    update: dict[str, object] = {
        "readability": readability,
        "target_geography": brief.target_geography,
        "time_horizon": brief.time_horizon,
    }
    if brief.product_note and brief.product_note.strip():
        note = ContextClaim(
            text=brief.product_note.strip(),
            kind="user_provided",
            confidence="high",
            status="not_applicable",
        )
        update["product_summary"] = [note, *context.product_summary]
    if readability == "thin":
        update["unknowns"] = [
            "The site returned almost no readable text, so describe the product.",
            *context.unknowns,
        ]
    return context.model_copy(update=update)


class ContextService:
    def __init__(
        self,
        fetcher: Fetcher,
        extractor: ContextExtractor,
        store: Store,
        provider_modes: dict[str, Mode],
        clock: Callable[[], datetime] = _now,
        max_pages: int = 8,
    ) -> None:
        self._fetcher = fetcher
        self._extractor = extractor
        self._store = store
        self._provider_modes = provider_modes
        self._clock = clock
        self._max_pages = max_pages

    def intake(
        self,
        raw_url: str,
        goal: str,
        initiated_by: str = "ui",
        brief: IntakeBrief | None = None,
    ) -> IntakeOutcome:
        """Raises UnsafeUrlError before any run exists; IntakeFailed after one is recorded."""
        seed = normalize_seed_url(raw_url)
        host = check_url_static(seed)
        web_mode = self._provider_modes["web"]
        run = RunReceipt(
            id=uuid.uuid4().hex,
            kind="context_intake",
            mode=web_mode,
            provider_modes={"web": web_mode},
            initiated_by=initiated_by,
            started_at=self._clock(),
            seed_url=seed,
        )
        self._store.save_run(run)
        try:
            return self._run_intake(run, seed, host, goal, brief or IntakeBrief())
        except IntakeFailed:
            raise
        except Exception as exc:  # noqa: BLE001 - any failure must close the run visibly
            return self._fail(run, f"{type(exc).__name__}: {exc}")

    def _run_intake(
        self, run: RunReceipt, seed: str, host: str, goal: str, brief: IntakeBrief
    ) -> IntakeOutcome:
        t = time.perf_counter()
        pages = crawl_site(seed, self._fetcher, self._max_pages)
        run.stage_ms["crawl"] = _ms(t)
        ok_pages = [p for p in pages if p.fetch_status == "ok" and p.text]
        run.pages_attempted = len(pages)
        run.pages_ok = len(ok_pages)
        run.page_failures = [
            PageFailure(url=p.url, status=p.fetch_status, error=p.error)
            for p in pages
            if p.fetch_status != "ok"
        ]
        # The model sees each page's title and body, so both are quotable evidence.
        page_texts = {p.url: f"{p.title}\n{p.text}" if p.title else p.text for p in ok_pages}
        self._store.save_run_pages(run.id, page_texts)

        t = time.perf_counter()
        if ok_pages:
            # A live model sometimes answers a readable site with nothing at all. That is a
            # failed step, never an empty profile that looks like a success.
            for _ in range(MAX_EXTRACTION_TRIES):
                result = self._extractor.extract(seed, goal, pages)
                draft = result.draft
                run.provider_modes["llm"] = result.mode
                if result.usage is not None:
                    run.llm_calls.append(
                        LlmUsageRecord(task="context_extraction", **vars(result.usage))
                    )
                if _has_claims(draft):
                    break
            else:
                if assess_readability(pages) == "ok":
                    self._fail(run, "the model returned no facts from a readable site")
        else:
            reasons = ", ".join(sorted({p.fetch_status for p in pages}))
            why = (
                f"Fixture mode has no fixture for {seed}. Run with WEB_MODE=live to read it."
                if any(p.error == "fixture_missing" for p in pages)
                else f"Could not retrieve any page from {seed} ({reasons})."
            )
            draft = ContextDraft(unknowns=[f"{why} Every field is unknown; describe the product."])
        run.stage_ms["extract"] = _ms(t)
        run.mode = combine_modes(run.provider_modes)

        t = time.perf_counter()
        context = BusinessContext.from_draft(
            draft,
            website_url=seed,
            domain=host.removeprefix("www."),
            user_goal=goal.strip(),
            pages=[_page_ref(p) for p in pages],
            mode=run.mode,
            run_id=run.id,
            provider_modes=dict(run.provider_modes),
        )
        context = ground_context(context, page_texts).model_copy(
            update={"status": "review_required"}
        )
        context = _apply_brief(context, brief, assess_readability(pages))
        run.stage_ms["ground"] = _ms(t)

        context_id = uuid.uuid4().hex
        self._store.insert_context_version(context_id, context)
        run.context_id = context_id
        run.unsupported_claim_count = len(context.unsupported_claims())
        run.outcome = "completed" if ok_pages and not run.page_failures else "completed_with_gaps"
        run.finished_at = self._clock()
        self._store.save_run(run)
        return IntakeOutcome(context_id, run.id, context)

    def _fail(self, run: RunReceipt, error: str) -> IntakeOutcome:
        run.errors.append(error)
        run.outcome = "failed"
        run.finished_at = self._clock()
        self._store.save_run(run)
        raise IntakeFailed(error, run.id)

    def get(self, context_id: str, version: int | None = None) -> BusinessContext:
        ctx = self._store.get_context(context_id, version)
        if ctx is None:
            raise ContextNotFound(context_id)
        return ctx

    def edit(self, context_id: str, changes: dict[str, list[str]]) -> BusinessContext:
        """Replace whole fields. Texts that match an existing claim keep its evidence;
        new texts become `user_provided` claims. Any edit re-opens review."""
        unknown = set(changes) - EDITABLE_FIELDS
        if unknown:
            raise InvalidEdit(f"not editable: {', '.join(sorted(unknown))}")
        current = self.get(context_id)
        try:
            edited = self._apply_edit(current, changes)
        except ValidationError as exc:
            raise InvalidEdit(f"invalid value: {exc.errors()[0]['msg']}") from exc
        self._store.insert_context_version(context_id, edited)
        return edited

    def _apply_edit(
        self, current: BusinessContext, changes: dict[str, list[str]]
    ) -> BusinessContext:
        update: dict[str, object] = {}
        for name, texts in changes.items():
            cleaned = [t.strip() for t in texts if t.strip()]
            if name == "unknowns":
                update[name] = cleaned
                continue
            existing = [current.company_name] if name == "company_name" else getattr(current, name)
            by_text = {normalize_for_match(c.text): c for c in existing if c is not None}
            new_claims = [
                by_text.get(normalize_for_match(t))
                or ContextClaim(
                    text=t, kind="user_provided", confidence="high", status="not_applicable"
                )
                for t in cleaned
            ]
            if name == "company_name":
                if len(new_claims) > 1:
                    raise InvalidEdit("company_name takes at most one value")
                update[name] = new_claims[0] if new_claims else None
            else:
                update[name] = new_claims
        update.update(
            version=current.version + 1,
            status="review_required",
            approved_at=None,
            approved_by=None,
        )
        return BusinessContext.model_validate(current.model_copy(update=update).model_dump())

    def approve(
        self,
        context_id: str,
        approver: str,
        acknowledge_unsupported: bool = False,
        expected_version: int | None = None,
    ) -> BusinessContext:
        """Approves the newest version; `expected_version` pins the version the reviewer saw."""
        current = self.get(context_id)
        if expected_version is not None and expected_version != current.version:
            raise VersionMismatch(expected_version, current.version)
        unsupported = current.unsupported_claims()
        if unsupported and not acknowledge_unsupported:
            raise UnsupportedFactsRemain([c.text for c in unsupported])
        if not current.has_usable_facts():
            raise EmptyProfile("no sourced or user-provided facts: describe the product first")
        update: dict[str, object] = {
            name: [c for c in getattr(current, name) if c.status != "unsupported"]
            for name in CLAIM_LIST_FIELDS
        }
        if current.company_name is not None and current.company_name.status == "unsupported":
            update["company_name"] = None
        update.update(
            version=current.version + 1,
            status="approved",
            approved_at=self._clock(),
            approved_by=approver,
        )
        approved = current.model_copy(update=update)
        self._store.insert_context_version(context_id, approved)
        return approved

    def versions(self, context_id: str) -> list[tuple[int, str, str]]:
        rows = self._store.list_context_versions(context_id)
        if not rows:
            raise ContextNotFound(context_id)
        return rows
