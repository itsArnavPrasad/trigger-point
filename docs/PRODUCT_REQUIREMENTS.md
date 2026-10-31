# Product Requirements Document

## Goal
Deliver a trustworthy, evidence-first GTM operating system, run from Trigger Point Office: from a website and goal, through strategy, research, approved execution and outcomes, to controlled learning.

## User story
"As a B2B founder, I want to paste my website and describe the customers I want, so Trigger Point can understand my product, find accounts with a reason to buy now, explain its reasoning, and prepare a campaign for me to approve."

## Functional requirements

### FR-1 Website intake
- Accept a public HTTP(S) URL, a goal, and optionally a product description, target geography and time horizon.
- Read JavaScript-rendered sites, or say plainly that the site could not be read.
- A profile with no supported or user-provided facts cannot be approved.
- Validate URL and prevent SSRF: block localhost, private IP ranges, link-local addresses, non-HTTP protocols, and unsafe redirects.
- Fetch a bounded set of relevant public pages with rate limits, timeouts, size limits, and a clear user agent.
- Store source URL, fetch time, page title, extracted text hash, and extraction status.
- Treat page contents as untrusted data, never as agent instructions.

### FR-2 Business context
- Produce a versioned `BusinessContext` with citations to website pages.
- Separate observed website facts from inferred positioning. Target claim classes: fact, user statement, assumption, hypothesis, recommendation.
- Show whether each fact came from the website, the user, a connected tool or model inference.
- Preserve the original answer and correction history.
- Mark confidence and unknown fields.
- Provide a review/edit step before prospecting.
- Preserve user-approved context separately from machine-generated suggestions.

### FR-3 Mission compiler
- Convert plain language into a validated typed plan.
- Support ICP, geography, size/stage, buyer titles, signals, exclusions, result count, freshness windows, budget, and output goal.
- Use provider autocomplete for enumerated filter values where available.
- Show filter assumptions, relaxation steps, and budget before expensive calls.
- If filters produce no results, relax one constraint at a time and record why.

### FR-4 Account discovery
- Use Crustdata Company Search and Company Identify via a provider adapter.
- Canonicalize and deduplicate by provider identity/domain, not display name alone.
- Persist raw response metadata safely and normalized fields.
- Keep source provenance and update timestamps.

### FR-5 Signals
- Model hiring, funding, executive changes, champion moves, technology adoption, relevant public posts, and company announcements when provider access supports them.
- Every signal must have type, event date if known, publication date, observed/retrieved timestamps, URL, title, publisher, excerpt, entity association, freshness, and verification status.
- Verification status: `VERIFIED`, `NEEDS_REVIEW`, `CONTRADICTED` or `STALE`.
- Score relevance, freshness, strength and source reliability separately. Explain the link between signal and need.
- Never infer an event date from a retrieval date.
- Expire or decay signals according to type-specific rules.

### FR-6 People and warm paths
- Search for roles related to the pain owner; do not default to CEO.
- See FR-17 for the buying committee.
- Verify current company and role as well as provider coverage allows.
- Warm paths are shown only when relationship evidence exists, e.g. shared employer/school or user-provided network data. Do not claim a relationship from a name match.
- Do not scrape or access private profiles outside authorized provider capabilities.

### FR-7 Scoring
- Score via pure deterministic code.
- Include version, factors, weights, hard rejection reasons, and data coverage.
- Missing data must not silently become a high score.
- Treat weights as hypotheses to be calibrated against real outcomes.

### FR-8 Case files
- One durable case file per canonical account and mission.
- Four sections: why account, why person, why now, why us.
- Every fact links to evidence; hypotheses are explicitly marked.
- Include next best action, campaign drafts, verifier log, run receipt, and state history.

### FR-9 Campaign plan
- Generate an intro request if a credible warm path exists; otherwise prepare a cold first touch.
- Provide email, optional LinkedIn note, and follow-ups with distinct angles.
- Use seller-approved proof points only.
- Keep drafts concise and relevant; do not fabricate familiarity, mutual connections, results, customer names, or buyer pain.
- Include source panel and claim-to-source mapping.

### FR-10 Verification
- Validate every factual claim in the case and outreach.
- Verify source existence, entity match, date/freshness, claim support, and relevance.
- If a claim fails: re-fetch once within budget, revise without the claim, or reject the draft.
- Show verifier outcome and reason.

### FR-11 Approval and external actions
- Default to dry-run.
- External sends and irreversible CRM actions require explicit approval of the exact recipient, channel, content, and action.
- Support suppression/opt-out checks and stop-on-reply semantics before enabling sends.
- Log who approved what, when, and which content hash was approved.

### FR-12 Watchers and follow-up
- Add watcher configuration after the core workflow is reliable.
- Show watch criteria, target entity, baseline, webhook/test state, estimated costs, and pause/delete controls.
- Test events must be labeled as test events.
- A watcher event creates a new signal and case update idempotently.

### FR-13 Audit and cost
- Show provider calls, credits/cost if exposed by provider, latency, cache hits, failures, and data coverage.
- Record request IDs and API version where available.
- Never report estimated cost as actual usage.
- Never count drafts as replies, meetings, opportunities, or revenue.

### FR-14 Trigger Point Office is the only UI
- All intake, questions, reviews, approvals, case files and results happen in Trigger Point Office. Clicking a character opens its dashboard. See `docs/GTMO_OFFICE_UI_PLAN.md`.
- The Office shows only real state. No fake progress, simulated tool activity or decorative lines that look like work.
- Statuses: Idle, Queued, Running, Waiting for input, Waiting for approval, Succeeded, Failed, Cancelled, Connection lost.
- Clicking an agent shows its real task, state, inputs, tools, outputs, evidence, errors and retries.
- Show integration health and last successful sync per provider.
- Refresh, reconnect and restart preserve missions.
- Fixture data is always labelled.

### FR-15 Market and category research
- Define category, direct and indirect competitors, substitutes and status quo.
- Primary sources first. Record source, publication date, event date, retrieval time, excerpt and relevance.
- Separate observed competitor facts from inferred strategy. Do not infer private metrics.
- Produce a competitor map, market gaps, differentiation hypotheses and open questions.

### FR-16 Versioned ICP and positioning
- An ICP has segments, must-haves, weighted preferences, disqualifiers, and confidence and evidence per criterion.
- Evaluate firmographic, operational, problem, value, budget, technographic, readiness, buying-process, reachability and economic dimensions where relevant.
- Without customer data, an ICP is labelled a hypothesis.
- Every version records date, author, changes and rationale. Users can accept, edit, reject and compare.
- Define value proposition, positioning, message pillars and proof. Flag claims needing customer proof or legal review.

### FR-17 Buying committee
- The ICP identifies the account; personas identify people. Do not assume one committee for every deal.
- Roles include user, champion, functional owner, economic buyer, sponsor, technical evaluator, security or legal reviewer, procurement, blocker and partner.
- Each persona records outcome, pain, risk, metrics, objections, influence, questions, evidence needs and call to action.
- Distinguish known people from inferred roles. Recommend a sequence. Each person gets a distinct purpose and message.

### FR-18 GTM motion and channels
- Recommend and justify a motion: founder-led, outbound, inbound, product-led, partnerships, community, content, events, channel, or a hybrid.
- Channel plan: audience, purpose, offer, timing, owner, cost, success metric.
- Use only channels with a real integration or a labelled manual workflow.
- Experiments: hypothesis, variants, metrics, decision rules.

### FR-19 Meetings and feedback
- Connect Wispr Flow MCP when authorized. It is read-only. Test a real meeting read before claiming the connection.
- Match meetings by verified identifiers. Keep source links. Separate statements from interpretation.
- Link insights to the ICP, messaging, opportunity and campaign version that produced the meeting.

### FR-20 Controlled learning
- Keep raw events apart from summarized memory. Follow the nine-step loop in the spec.
- Detect small samples, bias, attribution gaps and delays. Do not call a tactic successful from one reply.
- Material changes need approval. Every change is versioned and reversible. Never learn from fixtures.
- Users can inspect, correct, approve or delete memory.

### FR-21 Pipeline and CRM
- Define stages with entry and exit criteria. Track accounts through to closed and renewal.
- Separate provider events from inferred CRM status. Flag attribution uncertainty.
- Write to a CRM only through a connected integration under the approval policy.

### FR-22 Finance and unit economics
- Track spend by provider, channel, campaign, account and period, with currency, source, date, and actual vs estimated.
- Show budget, actual, forecast and variance, and unit costs where data exists.
- Never present pipeline as revenue or estimates as actual. Every metric traces to records and tested formulas.

## Non-functional requirements
- Typed validation at every provider boundary.
- Timeouts, bounded concurrency, retries with backoff, caching, idempotency.
- PII minimization and secret redaction in logs.
- Tenant isolation before multi-user launch.
- Deterministic offline tests using fixtures.
- Accessible UI in the Office with clear live/fixture status.
- Observability: structured logs, trace/run ID, stage timings, and explicit error states.

## Acceptance
The product definition of done is spec Part F, tracked in `docs/GTMO_AUDIT_REPORT.md`.

## MVP acceptance criteria
1. A user can submit a URL and a GTM goal, in the Office.
2. The system creates a reviewable business profile with source links.
3. A user can edit/approve the profile and compile a target plan.
4. At least one live Crustdata company search/identify path works when credentials and endpoint access are available.
5. A case file includes canonical account identity, score breakdown, evidence, and uncertainty.
6. Unsupported or stale claims are removed or marked unverified.
7. No external send can happen through the MVP.
8. A fixture/replay run can complete with no API keys and is clearly labeled.
9. Tests cover provider failures, duplicates, missing evidence, stale signals, and hard rejections.
