# Project Status

Checklist status: 67 working, 52 partial, 19 missing, 0 broken, 0 unverified, 0 not applicable of 138. See `docs/GTMO_AUDIT_REPORT.md`. Setup is in `README.md`.

## Current state
The core loop runs end to end:

website → sourced business context → strategy → versioned ICP → Crustdata discovery → signals, people and deterministic scores → four-why case files → verified outreach → hash-bound approval → test send and meeting → replies and meetings → reviewed insights → lessons → versioned change → measurement → keep or roll back.

Live: web fetching, GLM (Hyde), Gmail and Calendar on the test inbox, Wispr Flow reads, Crustdata. Crustdata runs live.

## Verification
| Command | Result |
|---|---|
| `uv run pytest` | passes, offline |
| `uv run ruff check .`, `uv run mypy` | clean |
| `uv run python -m evals.run_evals` | 30/30 |
| `office`: `npm test`, `npm run build` | pass |

Real runs are listed in `docs/GTMO_AUDIT_REPORT.md`, section 6.

**Not verified:**
- The Director running Check replies, Import from Wispr Flow and Review what we learned. Each read is held for a click, and the parts are proven separately.
- The loop on real results. It is proven on labelled fixture data, and test sends never teach.
- The **Send to test inbox** and **Book test meeting** buttons. Gmail and Calendar were tested through Claude Code; the buttons need a click on the held card.
- A held prompt inside a subagent.
- Case file, draft and gate on a live account. Schools found so far have no why-now signal.

## Known limits
- One case file and one draft per mission.
- Approval actor is a fixed string, and the gate relies on Claude Code permissions: `bypassPermissions` removes it.
- Loopback only. Not safe to host.
- Purely client-rendered sites give little text. Streamed Next.js pages are read correctly.
- Mail from a consumer Gmail account can land in spam.

## Implemented
- **Intake and context:**
  - SSRF-guarded bounded crawl.
  - Every claim is a quoted fact, an inference or user-provided; quote grounding covers the page title and body.
  - Versioned review and approval.
- **Mission:** GLM proposes, code compiles: a table-driven plan, free filters, a budget-sized search limit and the credit estimate.
- **Discovery:** endpoint probe, seller identity resolution, ranked search, relaxation, exclusion and dedupe with reasons.
- **Crustdata adapter:** company identify and search, job search, person search (minimal fields, never contact data), endpoint access. Typed errors, retries, a budget that fails closed, actual-vs-estimate receipts, record and replay.
- **Signals** (`signals-v1`):
  - Job postings into the persona's function are dated events (posted date plus last-seen date).
  - Headcount growth and open roles are metrics "as of" the provider refresh.
  - Freshness windows are within the 120-day policy; statuses are `active`, `expired` and `undated`.
  - Tech keywords named in a posting are fit evidence, with an excerpt.
- **Scoring** (`score-v1`, pure):
  - 0.35 fit + 0.35 timing + 0.20 reachability + 0.10 evidence quality.
  - Exponential decay on signal age; unknown components count as 0 and lower coverage.
  - Hard rejections; qualified / insufficient_evidence / rejected; tiers; deterministic tiebreak.
- **People:** persona title matching; the current employer must equal the account's Crustdata id. Individual contributors and stale employers are rejected with reasons.
- **Research run:** jobs, then signals, then a preliminary score, then people for the top 5, then the final score. Budget and permission problems skip a stage with a visible note. An explicit reference date keeps replay freshness stable.
- **Case file** (`case-v1`, deterministic):
  - Why account, why person, why now and why us, each item a cited fact, a labelled inference or an unknown.
  - "Why us" uses only approved, quote-verified seller facts.
  - Plus a warm-path statement, coverage gaps, route and next action, and an expiry date.
- **Drafts:**
  - GLM writes from the case evidence only, citing evidence ids, and never sees other prospects.
  - `verifier-v1` checks hook, citations, numbers, proof-point origin, entity, relative time, banned and fake-familiarity phrases, length, placeholders and contact data.
  - One revision, then rejection.
  - Human edits are re-verified.
  - Approval binds the content hash and never sends.
- **UI:** Trigger Point Office. Fixture data is labelled on every screen. Only http(s) URLs render as links.
- **Outreach without Crustdata:** named targets and audience-specific verified messages (Outreach page). A message is rechecked against current rules before it is prepared or approved.
- **Test send and meeting:** Gmail and Calendar through Claude Code, limited to `TRIGGER_POINT_TEST_RECIPIENTS` by a hook.
- **Strategy, ICP versions, pipeline, learning and finance:** see `docs/GTMO_AUDIT_REPORT.md`.
- **Evals:** `uv run python -m evals.run_evals`.
- **Replies and sequences:** Gmail threads parsed in code, opt-outs and bounces by rule, interest by a person; schedules, suppression, follow-ups with stop rules.
- **Meetings:** Wispr import with verified quotes, a review queue, and progress on each meeting.
- **Improvement loop:** `workflow/loop.py` and `workflow/feedback.py`, shown on the Learning page.
- **MCP tools:** 36 tools. 6 are ask-gated. Only workflow tools can change a mission.

## Known gaps
- **Why-now for schools:** job data does not cover them. See `docs/CRUSTDATA_INTEGRATION.md`.
- **Multiple hooks:** drafts may combine two hooks, although the policy says one. The verifier does not enforce this.
- **Not built:** follow-up bodies (only the angle plan exists), a LinkedIn note, and warm paths. There is no relationship data, and every case says so.
- **Which signals apply is not yet learned.** The ICP Strategist is told to reason about the buyer type before choosing `signal_types`. Across two live runs against Mumbai schools it chose `active_hiring` once and an honest empty list once; a model call is not deterministic, so either can happen. Outcomes from the outreach path (`workflow/outreach.py`) are not yet linked to which Crustdata signal justified the target, so the learning loop's `signal_type` comparison has nothing to learn from until that link is built.
- **Security:** DNS-rebinding window, which needs IP pinning before hosting. robots.txt is not consulted. Quote grounding proves the quote exists, not that it entails the claim.

- **Discovery vocabulary:** the post-filter that drops non-buyers uses education-leaning word lists, and applies only when the ICP names a buyer segment such as schools or hospitals. Other segments are not covered.
- **Parents:** no signal yet. The plan is explicit self-statements only, never age inference, and the data is thin.
- **Model variability:** the ICP step's signal choice differs between runs. A person can retry, and required fields stop it from skipping the topic keywords.
- **Credit budget:** each stage gets its own cap rather than one cap for the whole run.

## Next tasks
Follow `docs/GTMO_IMPLEMENTATION_ROADMAP.md`. What each gap needs is in `docs/GTMO_AUDIT_REPORT.md`, section 15.

## Decisions (and why)
- **Trigger Point Office is the only UI.** See `docs/GTMO_OFFICE_UI_PLAN.md`.
- **Hybrid runtime.** Measured GLM latency rules out an agent-loop critical path. The typed MCP tools keep the invariants in code.
- **Verifier rules come from reading real model output.** Flaws found by reading live GLM drafts become deterministic rules with tests.
- **Metric signals use as-of dates.** Growth and openings are measurements, not events. Their windows are capped by the 120-day policy.
- **Evidence ids are content-based.** The same fact gets the same id across runs, which replay and dedupe depend on. 
- **Explicit research reference date.** Replay is evaluated as of the recording date, so freshness verdicts don't drift with the calendar.
- **People search covers only the top 5 non-rejected accounts.** It costs 0.23 credits per result, so spend goes where reachability matters.
- **`draft_outreach` is allowed without a prompt, `approve_draft` is ask-gated.** A draft has no external effect and must pass the verifier; approval is the human decision.
- **Provider text is captured by a hook, not retyped.** A customer quote counts only if code finds it in the raw source.
- **Approval changes behaviour.** An approved change is guidance in a new strategy version, and new work receives it. One target in five stays out as a holdout.
- **Learning decisions have no MCP tool.** Only a person in the Office can approve a lesson or conclude an experiment.
- **Test sends go through a hook allowlist.** The guard sits outside the model and fails closed, so a prompt cannot widen it.
- **Messages are rechecked at the boundary.** A stored `verified` status is not trusted, because rules can tighten after a message passes.
