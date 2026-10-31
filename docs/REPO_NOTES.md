# Repository Inspection Notes

No source code from any reference repository has been copied into Trigger Point. Everything below records patterns that were **studied** and then **reimplemented independently**, or rejected. The clones live in the parent directory (`../`) and under `~/.claude/plugins/marketplaces/`. They were not re-cloned into `references/`.

Method: I read the licenses myself. Implementation reviews were done by read-only subagents with exact file paths, and claims backed only by a README are labelled. I did **not** run any reference repo's test suite.

## Crustdata Skills (official)
- **URL:** https://github.com/crustdata/skills (installed plugin at `~/.claude/plugins/marketplaces/crustdata-plugin`)
- **Commit SHA:** `865a946386342974df56279fc32ebc23044f0867`
- **License:** MIT. I found no additional terms.
- **Files inspected:**
  - `rules/crustdata-tool-selection.mdc`
  - `skills/sales-outreach/SKILL.md`, `skills/sales-prospecting/SKILL.md`, `skills/account-research/SKILL.md`
  - `skills/warm-path-workspace/references/{chain-scoring,dossier-schema}.md`
  - `*/evals/evals.json`
- **Important finding:** the skills drive Crustdata through the **Code-Mode MCP** (`callTool('company_identify', …)`), not REST. They are the authority for workflow, cost ordering and freshness. They are **not** the authority for REST paths or schemas, which come from the docs (see `CRUSTDATA_INTEGRATION.md`).
- **Useful patterns:**
  - Freshness: posts ≤ 60 days, funding/news ≤ 90 days, undated items kept separate and never silently dropped.
  - Free calls first: `company_identify`, autocomplete, credits. Enrich by `crustdata_company_id`, never by name, because fuzzy matches multiply the charge.
  - The "no hook" path: name which sources came back empty and never fabricate a hook.
  - Warm-path chains count only when work history overlaps by date. Formula: `hops = clamp((5-rank)+penalty,1,5)`, `strength = 100-(hops-1)*20`.
  - A fixed deal-role vocabulary.
- **Patterns rejected:** Code-Mode JS specifics, emoji tiers, and brand/template rules.
- **Code copied/adapted:** No.
- **Decision:** study only. The freshness windows, call ordering and eval cases become Trigger Point tests in Phases 4–6.

## Outbound Intelligence Engine (OIE)
- **URL:** https://github.com/Kazemkhani/outbound-intelligence-engine
- **Commit SHA:** `840f57ad7b64bdcd8a4f29a24f2bc11b41f5c2ad`
- **License:** Apache-2.0. There is no NOTICE file.
- **Stack:** TypeScript monorepo (Next 15, Prisma, Inngest), Vitest. The audit counted about 404 tests by grep but did not run them.
- **Files inspected:**
  - `packages/core/src/{scoring,scoring-engine,match,signal-windows}.ts`
  - `packages/integrations/src/{contracts,base}/*`
  - `packages/orchestration/src/{send-gate,waterfall}.ts`
  - `packages/sequencing/send-step.ts`
  - `apps/web/app/approvals/actions.ts`
  - `evals/`
- **Useful patterns:**
  - A pure `score(subject, icp, now)` with `known` and `coverage` per component.
  - Probabilistic-OR signal combining `1-Π(1-sᵢ)`, central per-type TTLs, and a `model_version` stamped on every score.
  - A total, pure send gate.
  - A typed provider error taxonomy with a `retryable` flag, jittered backoff with injected sleep, and an `HttpTransport` seam for fixtures.
- **Patterns rejected:**
  - Approval does not bind to content: no content hash, no approver, no audit row.
  - The cost cap fails open on a DB error.
  - Routes call vendors directly, bypassing the adapters.
  - Mappers pre-decay signals, which double-decays them.
  - The idempotency hash joins parts with spaces, which is ambiguous.
  - No SSRF or prompt-injection defence.
  - No Crustdata adapter exists.
- **Code copied/adapted:** No.
- **Decision:** reimplement the scoring shape and send gate in Phases 5–6 with the fixes above: bind approval to the draft hash, fail closed on cost, and break ties deterministically.

## YALC
- **URL:** https://github.com/Othmane-Khadri/YALC-the-GTM-operating-system
- **Commit SHA:** `5686d1f2f526346133f78eef3349fc5a655757b4`
- **License:** MIT. I found no NOTICE file.
- **Stack:** TypeScript, Drizzle/libSQL, Firecrawl, Vitest. The audit counted about 157 test files but did not run them.
- **Files inspected:**
  - `src/lib/onboarding/{flag-capture,rich-profile,confidence}.ts`
  - `src/lib/web/{fetcher,url-validator}.ts`
  - `src/lib/services/crustdata.ts` and the Crustdata adapters
  - `src/lib/qualification/pipeline.ts`
  - `src/lib/intelligence/*`
  - `gold-fixtures/`
- **Useful patterns:**
  - Forced-schema extraction with the rule "leave empty rather than fabricate".
  - User-supplied fields always override extracted ones.
  - A deterministic confidence blend that routes weak sections to human review.
  - A capability registry with fallback and a typed "tried these" error.
  - Deterministic gates run before any LLM step.
  - Schema-validated gold fixtures.
- **Patterns rejected:**
  - **The whole Crustdata adapter.** It uses legacy endpoints (`/screener/*`, `/v1/companies/search`), `Authorization: Token`, and **no `x-api-version`**, plus several field-mapping bugs.
  - The final qualification score comes from the LLM.
  - The credit preflight and the swallowed errors fail open.
  - The onboarding fetch skips the URL validator and follows redirects.
  - No prompt-injection boundary.
- **Code copied/adapted:** No.
- **Decision:** study only. Trigger Point's user-provided precedence and "unknown rather than guess" rules are reimplemented in slice 1.

## Anthropic Knowledge Work Plugins (sales)
- **URL:** https://github.com/anthropics/knowledge-work-plugins (installed plugin)
- **Commit SHA:** `2574e29377c7173d0cecffef29a6ecbd7f8ccb5d`
- **License:** Apache-2.0
- **Files inspected:** `sales/README.md`, and `sales/skills/{account-research,draft-outreach,account-tiering,lead-triage}/SKILL.md`
- **Useful patterns:**
  - Ask one question, otherwise use a labelled default.
  - Distinguish "blank" from "not queried".
  - Show suggested writes with evidence before making them.
  - Recipients come only from the user or the CRM, never from content.
  - Tiering rubric: fit 0–10 and engagement 0–10, with a stated cutoff.
- **Code copied/adapted:** No.
- **Decision:** study only. These shape the clarification-question cap (≤ 3) and the approval UX.

## OpenGTM
- **URL:** https://github.com/buildingopen/opengtm
- **Commit SHA:** `c9a7ad6bcedd1f0386373d7611f1334edc726429`
- **License:** MIT
- **Stack:** Python, Gemini, httpx. **There are no tests.**
- **Files inspected:** the `opengtm/` modules, `cli.py`, `analytics.py`, `qualify.py`, `message.py`, `docs/message-frameworks.md`
- **Useful patterns:** a per-dimension `breakdown` plus `reasons` in score output, and deterministic template selection.
- **Patterns rejected:**
  - LLM-asserted facts feed straight into scoring.
  - No SSRF protection (redirects are followed blindly).
  - The API token goes in a query string through `subprocess curl`.
  - Statistics are invented inside message templates.
  - No tests.
- **Code copied/adapted:** No.
- **Decision:** study only.

## Not inspected
- **obra/superpowers:** installed as a plugin (7.0.0) and used as a workflow. Its internals were not inspected because they're not needed.
- **TREG:** not cloned, deliberately. Its license restricts hosted or managed use, so it stays research-only pending legal review.
- **LangGraph / Firecrawl:** not needed yet. Slice 1 uses a bounded httpx fetch, and orchestration is an explicit service.
