# GTM OS Implementation Roadmap

Built from `docs/GTMO_AUDIT_REPORT.md`, following spec Part E.

**Rules.** One vertical slice at a time. Each phase ends with passing tests and a real run. Effort is a range, not a promise.

## Status
| Phase | Name | State | Effort |
|---|---|---|---|
| 1 | Office truth and control | **Built.** Closes with one full mission, which needs a Crustdata key | - |
| 2 | Business profile and strategy foundation | Mostly built. Sourced market research needs a search connector | 1 week |
| 3 | ICP and account discovery | Partly built. Live Crustdata needs a key | 2-3 weeks |
| 4 | Stakeholders, signals, case files | Partly built | 2-3 weeks |
| 5 | Campaign planning and approvals | Partly built. Gmail proven on the test inbox | 2-3 weeks |
| 6 | Meetings and feedback | Manual entry built. Calendar and Meet proven on the test inbox. Wispr needs access | 1-2 weeks |
| 7 | Learning and strategy evolution | Core built. Needs real outcomes | 2-3 weeks |
| 8 | Pipeline and finance | Core built by hand entry. CRM needs a connection | 2-3 weeks |
| 9 | Demo hardening | Not started | 1 week |

## Phase 1: Office truth and control
Fake activity is gone, intake is honest, and the Office starts, chats with and approves a real Director. Remaining gate: a person clicks through one full mission.

## Phase 2: Business profile and strategy foundation
- Rendering for client-rendered sites.
- Typed adaptive questions with typed answers.
- Claim classes: fact, user statement, assumption, hypothesis, recommendation.
- Sourced market research.

**Gate:** a real site, including a client-rendered site, yields a reviewed profile and plan, with origin shown for every claim.

## Phase 3: ICP and account discovery
- `IcpVersion` additions: segments, ten dimensions, weights, evidence per criterion.
- Compare versions.
- Live Crustdata: endpoint report, vocabularies, contract tests from recorded fixtures.

**Gate:** one live run on a real ICP, with every rejection explained. **Needs a Crustdata key.**

## Phase 4: Stakeholders, signals, case files
- Committee model with roles and persona profiles.
- Person verification.
- More signal sources, funding first.
- Signal status: VERIFIED, NEEDS_REVIEW, CONTRADICTED, STALE.
- Separate relevance, freshness, strength and reliability.
- Accounts view with many case files.

**Gate:** a case file shows at least two stakeholders with distinct roles, each explained.

## Phase 5: Campaign planning and approvals
- One message per named stakeholder, with sequences and stop rules.
- Suppression, opt-out and duplicate checks.
- Draft lifecycle states. Running experiments.
- An authenticated sending domain with SPF, DKIM and DMARC.
- Reply reading.
- Real recipients stay blocked until this phase passes its tests.

**Gate:** a reviewed campaign exists, and a test proves nothing reaches a real recipient without its exact approval.

## Phase 6: Meetings and feedback
- Connect Wispr Flow first, and read real tool names from it.
- Import with source links. Match to accounts by verified identifiers.
- Separate statements from interpretation. Add a review queue.

**Gate:** a real meeting is read and linked. **Needs Wispr access.**

## Phase 7: Learning and strategy evolution
- The rest of the spec's nine-step loop: lesson memory and baseline comparison.
- Versioned messaging.

**Gate:** a verified outcome produces a proposal; approval creates a version; rollback restores the old one.

## Phase 8: Pipeline and finance
- CRM connector where available. Pipeline model.
- Cost ledger: actual, estimated, attributed, missing.
- Claude Code run cost captured. Formula tests. Data-quality warnings.

**Gate:** every number traces to records, and no estimate shows as actual.

## Phase 9: Demo hardening
- Seeded data with a clear DEMO MODE label.
- Test empty, slow, failed, unauthorized and disconnected integrations.
- Check every click path. Reproduce from a clean start.

## Standing work
- Grow the evaluation set in `evals/`, with labelled live output.
- Validate agent reply JSON.
