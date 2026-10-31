# Trigger Point — Claude Code Project Instructions

## Mission
Build Trigger Point: an evidence-first GTM operating system. It helps a company decide who to sell to, why those buyers may need the product now, how to reach them, what happened, and what to improve next. The user gives a website and a business goal. Trigger Point studies the business, asks only questions that change a decision, builds a versioned strategy, runs approved tasks through connected tools, records outcomes, and uses verified outcomes to propose improvements.

**Trigger Point Office (`office/`) is the only UI and the live control room.** Claude Code is the execution harness. Trigger Point's backend owns durable state. MCP exposes typed tools. Hooks report lifecycle events. The UI shows real state only.

The full product spec is `docs/GTM_OS_PRODUCT_SPEC.md`. Current truth is `docs/GTMO_AUDIT_REPORT.md`. Do not claim a feature exists because the spec describes it.

## Who this is for
Read `docs/FOUNDER_CONTEXT.md` first. It covers who the founders are, the AI tutor startup Trigger Point is built for first (selling to schools versus parents), and the "we just press the trigger" philosophy, under which meetings get booked and briefed for us.

## Read before changing architecture
- `docs/GTM_OS_PRODUCT_SPEC.md` (the target)
- `docs/GTMO_AUDIT_REPORT.md` (what is true today)
- `docs/GTMO_IMPLEMENTATION_ROADMAP.md` (build order)
- `docs/GTMO_OFFICE_UI_PLAN.md` (how the only UI works)
- `docs/PRODUCT_STRATEGY.md`
- `docs/PRODUCT_REQUIREMENTS.md`
- `docs/ARCHITECTURE.md`
- `docs/DATA_MODEL.md`
- `docs/EVIDENCE_AND_VERIFICATION.md`
- `docs/CRUSTDATA_INTEGRATION.md`
- `docs/OUTREACH_POLICY.md`
- `docs/REPO_REUSE_POLICY.md`
- `docs/PROJECT_STATUS.md` (what is built and verified) and `docs/CLAUDE_HYDE_OPERATOR.md` (hybrid runtime)

## Non-negotiable engineering rules
1. **Do not build a generic mass-email SDR.** The product is account judgment + timing + evidence + campaign operations.
2. **Facts and hypotheses are different types.** A hypothesis may be useful but must be explicitly labeled as inference.
3. **No unsupported claims.** Every externally verifiable claim needs a URL, retrieved timestamp, relevant excerpt, and verification status.
4. **Scoring is deterministic code.** The LLM may extract facts or explain scores but must never be the authority that computes final scores.
5. **Human approval is default-deny.** Never send an email, LinkedIn message, or perform an irreversible external write without explicit approval of the exact action.
6. **Unknown is not false and is not permission to guess.** Preserve missing fields as `unknown` / `null`; surface coverage gaps.
7. **Provider isolation.** Crustdata and web providers live behind adapters with validated, normalized internal contracts.
8. **Cost and reliability are product features.** Add caching, request budgets, rate-limit handling, idempotency, timeouts, retries with backoff, and a run receipt.
9. **Never log secrets or unnecessary personal data.** Use synthetic test fixtures. Keep `.env` out of git.
10. **No silent mocks.** Replay mode must be explicitly marked and visually distinct from live mode.
11. **Small vertical slices.** Write a failing test, implement the smallest change, run relevant tests and linters, then summarize evidence.
12. **Do not blindly copy reference repos.** Read their license, dependencies, security posture, architecture, and relevant files first. Follow `docs/REPO_REUSE_POLICY.md`.
13. **The Office shows real state only.** No fake progress, simulated events or decorative lines that look like work in live mode. If events stop, say Idle or Connection lost.
14. **The Office is the only UI.** New user-facing work goes in the Office. Claude Office is reference only: reuse its MIT art, not its code.
15. **Learn only from verified outcomes.** Never from fixtures. No silent strategy change: propose, show evidence, approve, version, allow rollback.
16. **Never claim an integration works until a real test passes.** Use `UNVERIFIED` otherwise.
17. **Enforce rules in code, permissions and tests,** not in prompts alone. Hooks are telemetry and controls, never the workflow engine.

## Workflow
- Start with the smallest relevant task and inspect the existing code before editing.
- Use the Superpowers workflow where available: clarify requirements, create a plan, implement test-first, review, and verify.
- For new features, state acceptance criteria and failure modes before implementation.
- Prefer typed models, pure scoring functions, explicit state transitions, and provider contracts.
- Add tests for stale signals, missing evidence, duplicate entities, rate limits, provider errors, and rejected sends.
- Keep commits small and explain any trade-off.

## Implementation order
Follow `docs/GTMO_IMPLEMENTATION_ROADMAP.md`, one vertical slice at a time. Broad changes need the user's approval of the plan first.

## Definition of done
- Acceptance criteria are covered by tests.
- Data returned by providers is validated before use.
- Errors are visible and recoverable.
- Every score has a breakdown and version.
- Every claim can be traced to evidence or is labeled inference.
- External actions remain blocked unless the user approved the exact action.
- Docs and `.env.example` match actual behavior.
- Report commands run and their results; never claim tests passed if they were not run.
