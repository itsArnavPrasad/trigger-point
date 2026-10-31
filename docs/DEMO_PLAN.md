# Trigger Point Demo Plan

## Demo goal
Prove that Trigger Point handles an unfamiliar natural-language GTM request, makes auditable decisions, and creates useful work rather than just a lead list.

## Recommended scenario
Use a seller whose website clearly explains a B2B product, then ask Trigger Point to find companies with a relevant observable trigger. Example: a support-automation product seeking SaaS companies that are expanding customer support teams. Label any seeded/synthetic data.

## Two-minute flow
- **0:00–0:12 — Website input:** paste seller URL and state the outcome.
- **0:12–0:30 — Context profile:** show extracted positioning, ICP hypothesis, proof points, and one uncertainty the user can correct.
- **0:30–0:50 — Plan + spend:** show compiled filters, estimated cost, and exclusions.
- **0:50–1:10 — Account board:** show one qualified account and one rejected account with a clear reason.
- **1:10–1:35 — Case file:** reveal all four whys, signal timeline, evidence links, score breakdown, and verifier.
- **1:35–1:50 — Campaign package:** show warm-path preference if evidence exists, otherwise a cold draft with mapped claims.
- **1:50–2:00 — Receipt/watch:** show calls, credits, mode, and optionally a clearly labeled Watcher test event.

## Demo wow moments
1. Reject a superficially attractive account because the evidence is stale or no relevant buyer exists.
2. Remove a personalized claim because the source did not support it.
3. Show a warm intro only when a real shared-work/school relationship is evidenced.
4. Trigger a new case from a Watcher test event if that functionality is implemented.

## Honest demo rules
- Never represent fixture data as live.
- Never claim emails were sent if only drafts were created.
- Never claim revenue or meeting lift without observed outcomes.
- Never invent source URLs, dates, relationships, or provider costs.
- Do not make live external sending a demo dependency.

## Replay fallback
Record provider responses as sanitized fixtures during development. The Office labels fixture data on every screen. Replay should run the same normalization, scoring, verification, and UI path as live mode.

## Demo script
**Rehearsal, with no network:** `scripts/office.sh --fixture`. Every screen is labelled as fixture data, and Crustdata rows say "synthetic demo fixture".

1. **Intake.** New mission: `supportpilot.example` and a goal.
   - The profile shows quote-verified facts.
   - The deliberately false "90%" fact is struck through as unsupported.
   - Hidden prompt-injection text on the customers page never reaches the model.
2. **Approve the profile, then the ICP.** Show the criteria, personas, signals, exclusions and the credit estimate.
3. **Approve discovery.** 5 accounts. The seller itself and a duplicate are rejected with reasons.
4. **Research and score.**
   - **Ledgerloop, Quartzdesk, Brightlane:** qualified, with every score part explained.
   - **Orbitly:** rejected (*wow moment*). Its only "Head of Support" works elsewhere: `no_relevant_buyer`.
   - **Fernwood:** rejected for `no_fresh_why_now`.
5. **Open the Ledgerloop case file** on the Evidence Auditor. The four whys, each marked fact or inference, with coverage gaps.
6. **Draft for Quartzdesk** (*wow moment*). The first draft invents "30%". The verifier fails it with `unsupported_number`, and one revision passes. Approve the exact text. The card says it was not sent.

**Live with a real website:** add the Crustdata key, set all three modes to `live`, and run `scripts/office.sh`. Spend is capped at 5 credits per run. Capture fixtures with `CRUSTDATA_RECORD_DIR=fixtures/replay/crustdata`. If the network fails, replay the recording; it is labelled as replay.
