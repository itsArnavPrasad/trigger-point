# Slice 3: Signals, People, Deterministic Scoring, Case Files, Verified Drafts

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Take a discovery run to a ranked account board. Every account answers *why this account, why this person, why now, why us* from evidence. A first-touch draft passes a deterministic verifier before a human can approve it. Nothing is ever sent.

**Architecture:**
- One `ResearchService` run per discovery, with its own credit budget:
  1. Job postings for the plan's persona functions and tech keywords (`/job/search`).
  2. Signals derived deterministically from discovery fields and postings.
  3. A preliminary pure score.
  4. People for the top accounts (`/person/search`).
  5. The final score.
- Every fact lives in an **evidence registry** with stable ids. Signals, case items and draft claims reference evidence ids.
- The LLM writes only the "why us" bridge and the draft, and must cite evidence ids. A deterministic verifier checks each citation, number, freshness, entity and copy rule.

**Spec:** `docs/EVIDENCE_AND_VERIFICATION.md`, `docs/OUTREACH_POLICY.md`, `docs/DATA_MODEL.md` (Evidence, Signal, AccountCase, CampaignDraft), `docs/PRODUCT_REQUIREMENTS.md` FR-5 to FR-11, `CLAUDE.md`.

## Global Constraints
- **Event date vs as-of date:**
  - A job posting's `metadata.date_added` is its **event date**.
  - Provider metrics (headcount growth, openings count) have **no event date**. They are "as of" the provider's `updated_at` and are labelled that way.
  - Retrieval time is never used as an event date.
- **Freshness windows**, from `DEFAULT_FRESHNESS_DAYS`: job postings 30, funding 90, growth metrics 180. A signal outside its window is `expired` and contributes 0 to timing.
- **Score v1 (`score-v1`)** is a hypothesis, not calibrated:
  - `total = 0.35·fit + 0.35·timing + 0.20·reachability + 0.10·evidence_quality`, each component 0–100 and clamped.
  - Timing: `100·(1 − Π(1 − strength_i·exp(−age_i/τ_i)))`, with `τ = window/2`.
  - An unknown component counts as 0 and lowers `coverage`; it is never imputed.
  - Tiebreak: total desc, then timing desc, then provider id asc.
- **Hard rejections:**
  - `excluded`
  - `identity_unresolved`
  - `no_fresh_why_now` (no active signal)
  - `no_relevant_buyer` (people searched, none matched)
- **People:**
  - Store only name, current title, current employer id, profile URL, role start date and provider `updated_at`. No contact data.
  - The current employer must equal the account's `crustdata_company_id`.
- **Warm path:** none without relationship evidence. This slice has no relationship data, so every case says so explicitly.
- **Draft rules** (OUTREACH_POLICY plus the Crustdata sales-outreach skill):
  - At most 120 words, one hook, one bridge, at most one proof point, one ask.
  - Every number in the copy must appear in cited evidence.
  - Proof points come only from the approved context.
  - No banned phrases or fake familiarity.
  - No other prospect's name.
  - The hook evidence must be active.
- **Verifier outcome:** `pass | revise | reject`. On a failure there is one LLM revision with the findings, then reject.
- **Approval:** binds the sha256 of (recipient id, channel, subject, body). Any edit invalidates it. Approval never sends; there is no send code path.
- **Cost:** a research run budget (default `CRUSTDATA_RUN_CREDIT_BUDGET`) is checked before each call; job search runs before people search; people search covers only the top `PEOPLE_TOP_N = 5` accounts.

## Review Focus
1. A posting older than 30 days, or an undated metric, is presented as "why now". It must be marked expired or undated and never become a hook.
2. A person whose current employer differs from the account, e.g. a stale profile. Reject them; they must never appear as "why this person".
3. A draft quotes "45%" while the approved proof point says "up to 45%", or invents "60%". The number check fails the invented one; the verbatim proof point passes.
4. A draft mentions another prospect company from the same run. Reject as an entity mismatch.
5. A run budget too small for people search. Accounts are scored with reachability unknown and labelled `insufficient_evidence`, not rejected as "no buyer".

## Tasks
- **A. Crustdata Job and Person search.**
  - Typed, allowlisted request/response models (filter names from the docs; job responses use `company.basic_info.crustdata_company_id`).
  - Credit estimates: job 0.03/result; person 0.03 + 0.1 experience filter + 0.1 experience received.
  - Client methods with receipts, and replay fixtures.
- **B. Evidence registry and signals.** `Evidence` and `Signal` models; pure collectors from discovery fields and job listings; freshness, decay and dedupe keys.
- **C. Scoring engine v1.** A pure function returning a `ScoreBreakdown` with per-component detail strings, `known` flags, coverage, rejections and the version. Table-driven tests for the evaluation cases in `EVIDENCE_AND_VERIFICATION.md`.
- **D. People mapping.** Persona title-keyword table plus title matching; employer verification; reachability score.
- **E. ResearchService run.** Orchestrate A to D within budget; persist the run, evidence, signals, people and scores; UI account board with qualified, insufficient-evidence and rejected groups.
- **F. Case file.** Deterministic four-why assembly from evidence. LLM "why us" bridge, labelled inference and citing evidence ids. Recommended route and next action; expiry is the earliest hook expiry.
- **G. Draft, verifier, approval.**
  - LLM first-touch draft with a claim-to-evidence map.
  - Deterministic verifier, one revision, verifier log.
  - Content-hash approval.
  - Case page with an evidence panel.
- **H. MCP tools and skill.** `run_research`, `get_account_case`, `draft_outreach`, `approve_draft` (ask-gated). Update the `run-gtm-mission` skill.
- **I. Docs audit, replay fixtures, end-to-end replay test, status.**
