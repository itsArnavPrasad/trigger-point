# Slice 1 — Website → Sourced Business Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A user submits a website URL + revenue goal and gets a reviewable, source-grounded `BusinessContext` they can edit and approve, in replay mode with no API keys, and in live mode when keys exist.

**Architecture:** Python package `trigger_point` (src layout). Typed stages: `url_guard` (SSRF policy) → `Fetcher` protocol (`SafeHttpFetcher` live / `FixtureFetcher` replay) → `extract` (HTML → page text + candidate links) → `ContextExtractor` protocol (`AnthropicContextExtractor` live / `ReplayContextExtractor`) → deterministic `ground_context` (every "fact" must quote an excerpt found in the cited page) → SQLite store → FastAPI JSON API + server-rendered review UI. Mode (live/replay) is a single explicit setting stamped on every run and shown in the UI.

**Tech Stack:** Python 3.12 (uv), FastAPI, Pydantic v2, httpx, BeautifulSoup4, Jinja2, anthropic SDK, stdlib sqlite3; pytest, ruff, mypy.

**Spec:** `docs/PRODUCT_REQUIREMENTS.md` (FR-1, FR-2, FR-13, MVP criteria 1–3, 8), `docs/EVIDENCE_AND_VERIFICATION.md`, `CLAUDE.md`.

## Global Constraints

- Python `>=3.12`; run everything through `uv run`.
- Only allow `http`/`https`; ports 80/443 only; no userinfo in URLs.
- Block loopback, private, link-local, multicast, reserved, unspecified, CGNAT (100.64/10), IPv4-mapped IPv6 of any of those — checked on **every resolved address of every redirect hop**.
- Fetch limits: ≤ 5 redirects, 10 s timeout per request, 2 MB body cap, `text/html` or `text/plain` only, ≤ 8 pages per site, same registrable host only, UA `TriggerPointBot/0.1 (+contact: set TRIGGER_POINT_CONTACT)`.
- Fetched content is untrusted data: never interpolated into instructions; delimited, and delimiter-collisions neutralised.
- A claim of kind `fact` must carry `source_url` + `excerpt`; if the excerpt is not found in that page's stored text it is marked `unsupported` (never silently kept as verified).
- `retrieved_at` is the fetch time; never used as an event date.
- `mode` ∈ {`live`,`replay`} is required on every run record and visible on every UI page.
- `ENABLE_EMAIL_SEND` / `ENABLE_LINKEDIN_SEND` default false; nothing in this slice sends anything.
- No secrets in logs or responses; API key values never rendered.

## Review Focus

1. Hostname that resolves to a private IP only after a redirect (e.g. public → `http://169.254.169.254/`) → must be refused, run records `blocked_redirect`.
2. Site with zero usable pages (all 4xx, non-HTML, or empty text) → context is created with every field unknown and a visible coverage gap, not a crash or invented content.
3. Page text containing "ignore previous instructions…" → treated as data; any claim whose excerpt is not in the page is `unsupported`.
4. User edits a field after extraction → stored as `user_provided`, machine draft preserved, approval creates a new immutable version.
5. Replay run rendered in UI → conspicuous `REPLAY MODE` banner; live run never shows it.

---

### Task 1: Baseline project, settings, health

**Files:** Create `pyproject.toml`, `src/trigger_point/__init__.py`, `src/trigger_point/config.py`, `src/trigger_point/api/app.py`, `tests/test_config.py`, `tests/test_health.py`.

**Interfaces — Produces:** `Settings` (frozen dataclass) with `mode: Literal["live","replay"]`, `database_url`, `anthropic_api_key: SecretStr|None`, `crustdata_api_key: SecretStr|None`, `enable_email_send: bool`, `enable_linkedin_send: bool`; `load_settings(env: Mapping[str,str]) -> Settings`; `create_app(settings, deps) -> FastAPI`.

- [ ] Tests: default env → `mode == "replay"`, sends disabled; `LIVE_PROVIDER_MODE=true` without `CRUSTDATA_API_KEY`/`ANTHROPIC_API_KEY` → `ConfigError`; `REPLAY_MODE=true` and `LIVE_PROVIDER_MODE=true` together → `ConfigError` (ambiguous); `repr(settings)` contains no key value; `GET /health` → `{"status":"ok","mode":"replay"}`.
- [ ] Implement; run `uv run pytest -q`, `uv run ruff check`, `uv run mypy src`; commit.

### Task 2: URL guard (SSRF policy)

**Files:** Create `src/trigger_point/security/url_guard.py`, `tests/security/test_url_guard.py`.

**Interfaces — Produces:** `Resolver = Callable[[str], list[str]]`; `normalize_seed_url(raw: str) -> str` (adds `https://` when scheme missing, lowercases host, strips fragment); `check_url(url: str, resolver: Resolver) -> None` raising `UnsafeUrlError(reason: str)`.

- [ ] Tests (parametrised): rejects `ftp://`, `file://`, `javascript:`, `http://user:pw@x.com`, port 8080, `localhost`, `127.0.0.1`, `10.1.2.3`, `172.16.0.1`, `192.168.1.1`, `169.254.169.254`, `100.64.0.1`, `0.0.0.0`, `[::1]`, `[fc00::1]`, `[::ffff:127.0.0.1]`, hostname whose resolver returns `["93.184.216.34","10.0.0.5"]` (any private ⇒ reject), resolver raising `OSError` ⇒ `UnsafeUrlError("dns_failure")`; accepts `https://example.com/` resolving to public IP; `normalize_seed_url("Acme.com/pricing#x") == "https://acme.com/pricing"`.

### Task 3: Safe bounded fetcher

**Files:** Create `src/trigger_point/web/fetcher.py`, `tests/web/test_fetcher.py`.

**Interfaces — Produces:** `FetchResult` (url, final_url, status: `ok|http_error|blocked|blocked_redirect|timeout|too_large|unsupported_type|network_error`, http_status, content_type, text, retrieved_at, sha256, error); `Fetcher` protocol `fetch(url) -> FetchResult`; `SafeHttpFetcher(client: httpx.Client, resolver, max_bytes, max_redirects)`; `FixtureFetcher(root: Path)` mapping `https://host/path` → `root/host/path/index.html`.

- [ ] Tests with `httpx.MockTransport`: redirect to private IP → `blocked_redirect`, the private host is never requested; 6 redirects → `http_error` "too_many_redirects"; body > max → `too_large`; `application/pdf` → `unsupported_type`; `httpx.ReadTimeout` → `timeout`; 404 → `http_error` with 404; success sets `sha256` of text and timezone-aware `retrieved_at`. Fetcher never raises for network outcomes.

### Task 4: HTML extraction and page selection

**Files:** Create `src/trigger_point/web/extract.py`, `src/trigger_point/web/crawl.py`, `tests/web/test_extract.py`, `tests/web/test_crawl.py`.

**Interfaces — Produces:** `extract_page(html: str, base_url: str) -> ExtractedPage(title, text, links)` (drops script/style/noscript/svg/template, collapses whitespace, caps text at 40 000 chars); `select_pages(seed: str, links: list[str], max_pages: int=8) -> list[str]` (same host incl. `www.` variant, no query strings/fragments/assets, ranked by path keywords product/platform/features/solutions/use-cases/pricing/customers/case-studies/integrations/about/security, seed first, dedup); `crawl_site(seed, fetcher) -> list[PageRecord]`.

- [ ] Tests: malformed HTML still yields text; `<script>` text excluded; offsite, `mailto:`, `.pdf` and `#frag` links excluded; ranking puts `/pricing` above `/blog/post-1`; empty HTML → empty text, no crash; `crawl_site` records every attempted page including failures.

### Task 5: Evidence-carrying BusinessContext + deterministic grounding

**Files:** Create `src/trigger_point/models/context.py`, `src/trigger_point/context/grounding.py`, `tests/context/test_grounding.py`.

**Interfaces — Produces:** `ClaimKind = Literal["fact","inference","user_provided"]`; `GroundingStatus = Literal["supported","unsupported","not_applicable"]`; `ContextClaim(text, kind, source_url|None, excerpt|None, confidence: Literal["high","medium","low"], status)`; `BusinessContext` fields per `docs/DATA_MODEL.md` (company_name, domain, product_summary, value_propositions, use_cases, target_segments, buyer_personas, customer_pains, differentiators, proof_points, competitors, exclusions — each `list[ContextClaim]`; `unknowns: list[str]`; `clarification_questions: list[str]` ≤ 3; `pages: list[PageRef]`; `status: draft|review_required|approved|archived`; `version`); `ground_context(ctx, pages: dict[url, text]) -> BusinessContext`.

- [ ] Tests: fact with excerpt present (case/whitespace-insensitive) → `supported`; fact with excerpt absent → `unsupported`; fact citing a URL not in crawled pages → `unsupported`; fact missing excerpt → `unsupported`; inference → `not_applicable` regardless of excerpt; >3 clarification questions → validation error; grounding is pure (input unchanged).

### Task 6: Context extractors (replay + Anthropic) and untrusted-content prompt

**Files:** Create `src/trigger_point/context/extractor.py`, `src/trigger_point/context/prompt.py`, `tests/context/test_extractor.py`, `tests/fixtures/replay/contexts/<domain>.json`.

**Interfaces — Produces:** `ContextExtractor` protocol `extract(seed_url, goal, pages: list[PageRecord]) -> ExtractionResult(context, usage: LlmUsage|None)`; `ReplayContextExtractor(root)` (missing fixture → `ReplayFixtureMissing`, never a fabricated context); `AnthropicContextExtractor(client, model)` using forced tool output validated by Pydantic; `build_untrusted_block(pages) -> str` wraps each page in `<page url=… index=…>` and neutralises any `</page` in content.

- [ ] Tests: replay fixture loads and validates; missing fixture raises; prompt builder neutralises `</page>` injection; Anthropic extractor with a fake client returning tool input → valid `BusinessContext`; fake client returning schema-invalid output → `ExtractionError` (no partial context stored).

### Task 7: Store, intake service, review/approve API

**Files:** Create `src/trigger_point/store/db.py`, `src/trigger_point/context/service.py`, `src/trigger_point/api/routes_context.py`, `tests/api/test_context_api.py`.

**Interfaces — Produces:** `Store(path)` with `save_context`, `get_context(id, version=None)`, `list_versions`, `save_run`, `get_run`; `IntakeService.run(url, goal) -> (context_id, run_id)`; routes `POST /api/contexts`, `GET /api/contexts/{id}`, `PATCH /api/contexts/{id}` (field edits → `user_provided` claims, version+1, status `review_required`), `POST /api/contexts/{id}/approve` (new immutable version `approved`; refuses if any `unsupported` fact remains unless explicitly `acknowledge_unsupported=true`, which drops them), `GET /api/runs/{id}` (receipt: mode, pages attempted/ok/failed, LLM usage if reported, timings, errors).

- [ ] Tests: unsafe URL → 422 with reason, no run created; all pages fail → context created, every list empty, `unknowns` explains coverage gap; edit then approve → v3 approved, v1 machine draft still retrievable; approve with unsupported facts → 409; run receipt `mode == "replay"`.

### Task 8: Review UI + replay demo fixture + docs

**Files:** Create `src/trigger_point/api/routes_ui.py`, `src/trigger_point/api/templates/{base,index,context}.html`, `tests/fixtures/replay/sites/supportpilot.example/**`, `tests/api/test_ui.py`; modify `.env.example`, `README.md`, `docs/PROJECT_STATUS.md`.

- [ ] Tests: replay context page contains `REPLAY MODE` banner, every fact renders its source link and grounding badge, unsupported facts are visually flagged, inference items labelled "Inference"; live-mode render has no banner.
- [ ] End-to-end: `uv run pytest` green; `uv run uvicorn trigger_point.api.app:app` serves the flow on the synthetic `supportpilot.example` site with no keys.
