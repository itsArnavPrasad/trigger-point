# Product Strategy

> **Target vs today.** This document states the target product. `docs/GTM_OS_PRODUCT_SPEC.md` is the full specification, and `docs/GTMO_AUDIT_REPORT.md` says what exists now. About one quarter of the target exists.

## 1. Product thesis

Trigger Point is an evidence-first GTM operating system. It helps a company decide who to sell to, why those buyers may need the product now, how to reach them, what happened, and what to improve next. The differentiator is not merely personalized copy. It is the judgment that determines which accounts deserve attention, why the timing is meaningful, which person owns the problem, and which approach is most credible, followed by learning from what actually happened.

**Trigger Point Office is the product surface:** a live control room where real agents do real work. It is the only UI.

**Positioning:** "Give Trigger Point your website and revenue goal. It researches the right accounts, proves why they matter now, finds the best route in, and prepares a campaign you can trust."

## 2. The first-run experience

### Step A — Website intake
In the Office, the user enters their company URL, a goal, and optionally a product description, target geography and time horizon. Crawl only relevant public pages: home, product/features, use cases, pricing, customers/case studies, integrations, about, and selected blog pages.

### Step B — Draft business context
Extract:
- product and category
- target segments and use cases
- customer pains and desired outcomes
- buyer, champion, user, blocker personas
- value propositions and differentiators
- customer proof points and permitted metrics
- competitors and alternatives, when supported
- geography, company size, maturity, and exclusions
- known constraints and uncertainty

Show a review card in the Office. Ask only questions whose answers can change a decision, and never ask for what reliable sources already provide. Never treat scraped copy as authoritative if it is ambiguous. Keep each extracted item with source URL and confidence.

### Step C — Research the market
Define the category, competitors, substitutes and the status quo from primary sources. Separate observed facts from inferred strategy. Then draft positioning and a versioned GTM plan: the motion, channels and messaging that fit the business. Use the simplest motion that fits.

### Step D — Compile a GTM mission
Turn the user's request into a typed `GTMPlan`: ICP filters, personas, signals, exclusions, geography, target count, campaign goal, channels, freshness limits, research budget, and output format. Show assumptions and estimated provider spend before executing.

### Step E — Research and qualify
Discover accounts; resolve identity; apply hard filters; enrich only shortlisted accounts; collect dated signals; find likely buyers; investigate warm paths only where available; then score using deterministic code.

### Step F — Case files and campaign plan
Each account case file answers:
1. Why this account?
2. Why this person?
3. Why now?
4. Why us?

Each includes evidence, uncertainty, a recommended route, drafts, next step, expiry/recheck date, score breakdown, and run cost.

Map the buying committee, not one contact. Each stakeholder gets a role-specific purpose and message.

### Step G — Approval and execution
Generate approval-ready drafts and optional CRM drafts/records. Never send automatically by default. Run only approved tasks, through connected tools.

### Step H — Meetings and outcomes
Import meeting insights through Wispr Flow's read-only MCP when authorized. Record outcomes such as reply, meeting, opportunity, disqualification, and opt-out. Do not call drafts, opens, or generated contacts revenue.

### Step I — Learning and finance
Propose changes to the ICP, messaging, qualification and channels from verified outcomes, with evidence. A human approves material changes; each creates a version and can be rolled back. Track spend and unit economics, and never present an estimate as actual or pipeline as revenue.

## 3. Target users
- Founder-led B2B companies with small GTM teams
- Boutique outbound/revenue agencies
- GTM engineers and RevOps operators
- Early-stage teams that need account research but cannot justify a large data-operations team

Build one vertical slice at a time, starting with one ICP and one outbound motion. The product scope is wider than that first slice, but no slice ships untested.

## 4. MVP promise
Given a website and a request, Trigger Point can produce a small ranked batch of qualified accounts with source-backed case files and approval-ready outreach. It should explain why it rejected accounts as clearly as why it selected them.

## 5. Product principles
- Show evidence for important claims
- Separate facts, user statements, assumptions, hypotheses and recommendations
- Store source URLs, event dates, retrieval dates, excerpts and confidence
- Ask a question only when its answer can change a decision
- Use the simplest GTM motion that fits the business
- Keep humans in control of consequential external actions
- Make strategy changes visible and reversible
- Learn from outcomes; do not silently rewrite strategy on one noisy result
- Keep a full audit trail for tools, tasks, decisions, costs and approvals
- Never claim an integration works until it passes a real test
- Show only real work in the Office
- Precision before volume
- Evidence before eloquence
- Fresh signals before generic personalization
- Warm paths before cold approaches, when reliably known
- Transparent scores rather than opaque AI judgments
- User-approved external actions
- Cost and uncertainty visible throughout
- Outcome tracking over vanity metrics

## 6. Differentiation
| Commodity SDR behavior | Trigger Point behavior |
|---|---|
| Starts from a static lead list | Starts from the seller's actual website, positioning, and goal |
| Writes a generic message per contact | Builds an account-level evidence case before writing |
| Uses an LLM to decide who is a good lead | Uses explicit, versioned scoring rules and hard disqualifiers |
| Treats inferred pain as a fact | Labels hypotheses and cites supporting signals |
| Sends volume by default | Prepares small, high-relevance batches for approval |
| Forgets after the sequence | Tracks outcomes and monitors future signals |
| Reports drafts created | Reports approved, sent, replied, meetings, opportunities, cost and attribution confidence |

## 7. Initial niche
Choose a demo niche where the seller's value proposition maps cleanly to observable buying signals. Example: a B2B support-automation company targeting SaaS firms hiring support representatives or expanding customer operations. Keep this as a demo scenario, not a hard-coded product assumption.

## 8. Success metrics
Leading indicators:
- % of claims with valid supporting evidence
- % of qualified accounts with a valid target persona
- reviewer acceptance rate of account cases and messages
- false-positive / false-negative rate from human review
- time from mission input to verified case file
- credits and latency per qualified account

Business outcomes:
- positive reply rate
- meetings booked and held
- qualified opportunities created
- pipeline generated and won revenue
- cost per qualified opportunity
- performance by segment, signal type, persona, and message angle

Keep actual outcomes separate from estimates. Do not claim lift until measured against a baseline or controlled comparison.
