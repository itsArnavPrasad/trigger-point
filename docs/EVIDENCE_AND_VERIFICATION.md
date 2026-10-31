# Evidence, Claims, Scoring, and Verification

## The evidence contract
Every factual claim displayed to the user must be linked to evidence. Minimum evidence fields:
- `claim`
- `source_url`
- `source_title` / publisher if available
- `published_at` when known
- `retrieved_at`
- `supporting_excerpt`
- `entity_id` or a clear canonical entity association
- `status`
- `verification_method`
- `confidence`

A retrieval timestamp is not the event date. Do not convert "page fetched today" into "the event happened today."

**Target signal status:** `VERIFIED`, `NEEDS_REVIEW`, `CONTRADICTED`, `STALE`. The target also stores publication date, event date and title. **Today:** audit-v1 reports `verified`, `user_provided`, `stale`, `undated`, `entity_mismatch` and `unverifiable`; it has no contradiction check; and it proves source, entity, date and freshness, not that a page says what an excerpt says.

## Claim classes
Keep these apart: fact, user statement, assumption, hypothesis, recommendation. Today's code has fact, inference and user_provided.

## Fact vs hypothesis
**Fact:** "The company currently lists four open customer-support roles" — only if the cited job records support that exact statement.

**Hypothesis:** "The company may be experiencing support workload pressure and could be evaluating automation." This is an inference and must be displayed as such.

**Seller fit hypothesis:** "Trigger Point believes the product may be relevant because the company is expanding its support team." This is not proof that the account has budget or intent.

## Claim verification sequence
1. Check the source is retrievable or use a recorded provider source with stable URL/ID.
2. Confirm it is about the canonical entity, not a similarly named company.
3. Check the source excerpt supports the exact wording.
4. Check event date and freshness policy.
5. Check whether the statement is fact, inference, or unknown.
6. Confirm any seller proof point comes from the user-approved BusinessContext.
7. Run copy-policy checks.
8. If invalid, retry once within budget, revise without the claim, or reject the draft.
9. Record the reason in `verifier_log`.

## Starting freshness policy
Use these as configurable initial assumptions, not universal truths:
- Social post/person activity: 60 days
- Funding/news: 90 days
- Job postings: verify currently open when possible; otherwise mark stale/uncertain
- Role/current-employer evidence: recheck before outreach where feasible
- Any signal older than 120 days: normally disqualify from a "why now" hook unless the event remains active and current evidence proves it

Show signal age and expiry. Allow signal-type-specific policy configuration.

## Example deterministic score
A starting hypothesis, not a calibrated probability:

`score = 0.35 * fit + 0.35 * timing + 0.20 * reachability + 0.10 * evidence_quality`

Each component is normalized 0–100. A timing score can combine signal strengths with exponential age decay. A simple form is:

`timing = 100 * (1 - product(1 - weight_i * exp(-age_days_i / tau_i)))`

Implement the exact formula in tested code, clamp outputs, and version weights. Never let the LLM output the final numeric score.

### Suggested components
- **Fit:** match to ICP, geography, stage, company size, use case, exclusions.
- **Timing:** number, type, strength, freshness and corroboration of relevant signals.
- **Reachability:** suitable person found, role confidence, verified warm route when known.
- **Evidence quality:** source quality, freshness, entity confidence, and claim coverage.

### Hard rejection examples
- canonical identity unresolved or conflicting
- explicit exclusion/suppression match
- no relevant buyer/persona and no viable way to identify one
- all proposed "why now" signals are stale or unsupported
- case relies on unsupported critical claims
- seller's product proof does not support the proposed claim

## Auditability
Every case needs:
- score version and component breakdown
- evidence and missing fields
- verifier decisions
- provider calls and cost receipt
- state transitions
- rejection reason when rejected
- exact draft content hash and approval status

## Evaluation set
Build synthetic, labeled test cases for:
- strong fit + recent signal
- strong fit + stale signal
- weak fit + exciting news
- duplicate company names/domains
- person changed jobs
- empty search
- contradictory evidence
- unsupported personalization
- no buyer found
- provider timeout / rate limit
- warm path evidence absent
- replay-mode data accidentally presented as live

Measure precision of accepted cases, claim support rate, stale-hook rejection rate, and false-rejection rate. Keep benchmark datasets synthetic or appropriately permissioned.
