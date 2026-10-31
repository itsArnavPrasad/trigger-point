# Slice 2: Hyde LLM, Crustdata Discovery, Mission Compiler, MCP Operator

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Live business-context extraction on Hyde (GLM 5.3 Flash). Then a typed, budgeted Crustdata identify/search adapter (replayable), a mission compiler from an approved context to a `GTMPlan` and a Crustdata search request, and an MCP server so a `claude-hyde` session can operate the same core. Everything it does appears in the UI.

**Architecture (decided 2026-10-31: hybrid):** Trigger Point code owns the pipeline. Judgment steps are single bounded structured-LLM calls behind `StructuredLlm` (Hyde live / fixture replay / recording). Providers are typed adapters with transport-level replay, so replay runs the same normalisation code. Each provider has its own live/replay mode, stamped on every run and shown in the UI. Claude Code on Hyde is an operator that drives the system through MCP tools; it is never the only execution path.

**Tech Stack:** as slice 1, plus the `mcp` Python SDK (Task 5 only).

**Spec:** `docs/PRODUCT_REQUIREMENTS.md` FR-3, FR-4, FR-13; `docs/CRUSTDATA_INTEGRATION.md` (Verified API facts); `docs/ARCHITECTURE.md`.

## Global Constraints
- Provider modes: `WEB_MODE`, `LLM_MODE`, `CRUSTDATA_MODE` ∈ {live, replay}, defaulting to replay. Legacy `LIVE_PROVIDER_MODE`/`REPLAY_MODE` are refused with a migration message.
- Run mode is `live` only if every provider used was live, `replay` if every one was replay, and `mixed` otherwise. Any replay provider shows a banner naming it.
- Hyde: `POST {HYDE_BASE_URL}/chat/completions`, `response_format.json_schema` (strict), model `hyde/glm-5.3-flash`, `max_tokens` 16000, read timeout 300 s. GLM is a reasoning model, so `finish_reason=length` means no answer.
- Crustdata: base `https://api.crustdata.com`, headers `authorization: Bearer`, `x-api-version: 2025-11-01`. Search is at most 100 results per ranked page. Operators include `=<`/`=>`.
- Credits: a pre-flight estimate must fit the remaining run budget, or the call is refused (fail closed). Actual usage comes only from `X-Credits-Used`.
- Retries: 429 waits `x-ratelimit-reset` plus jitter; 5xx/timeout use exponential backoff; at most 2 retries. 401/402/403 are terminal.
- Doc-derived fixtures are marked `"_source": "docs.crustdata.com example"` and are never presented as recorded live data.

## Review Focus
1. Identify returns several `confidence_score: 1` matches for one domain (showcase pages): resolve to the `/company/` page if exactly one, otherwise report it ambiguous, never picking the first.
2. Empty search result vs 403 endpoint-disabled vs 402 out of credits: three distinct, visible outcomes.
3. The LLM proposes a mission filter outside the allowed vocabulary (an unknown field or operator): code rejects it and records an assumption. It never reaches the HTTP client.
4. Hyde returns `finish_reason=length` or non-JSON: typed `LlmError`, the run is failed, no partial context.
5. The mode banner names exactly which providers were replay in a mixed run.

### Task A: Provider modes, `.env` loading, `StructuredLlm` (Hyde, replay, recording)
Files: `src/trigger_point/config.py`, `src/trigger_point/llm/{__init__,base,hyde,replay}.py`, `src/trigger_point/context/extractor.py`, tests.
Produces: `Settings.provider_modes: dict[str, Mode]`; `StructuredLlm.complete(req: LlmRequest[T]) -> LlmResponse[T]`; `LlmContextExtractor(llm)`.

### Task B: Crustdata adapter (identify, search, endpoint access)
Files: `src/trigger_point/providers/crustdata/{models,client,errors,replay,normalize,identity}.py`, `fixtures/replay/crustdata/*.json`, tests.
Produces: `CrustdataClient.identify_companies / search_companies / endpoint_access`, returning `ProviderResult[T]` with a receipt; `resolve_identity(result, queried_domain) -> Resolved | Ambiguous | NotFound`; `Company` (normalised).

### Task C: Mission compiler
Files: `src/trigger_point/mission/{models,compiler,service}.py`, API routes, UI page, tests.
Produces: `GTMPlan`; `MissionDraft` (LLM wire); `compile_search_request(plan) -> CompanySearchRequest`; `relaxation_steps(plan)`; credit estimate.

### Task D: Discovery run
Identify the seller (exclude self), search with the compiled plan, normalise, dedupe by `crustdata_company_id` / primary domain, persist accounts and a receipt, and show the account list in the UI.

### Task E: Trigger Point MCP server for `claude-hyde`
Tools: `start_context_intake`, `get_context`, `edit_context`, `approve_context`, `compile_mission`, `run_discovery`, `get_run`. A project `.mcp.json` and a skill describing the operator workflow.
