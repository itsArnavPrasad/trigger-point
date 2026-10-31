# Trigger Point GTM Operating System --- Product Checklist and Claude Code Audit Prompt

Version: 1.0 Purpose: Audit the current implementation before changing
it. Then produce a verified gap analysis and a staged implementation
plan. Style: ASD-STE100-inspired. Use short sentences. Use direct
instructions. Define technical terms when needed.

------------------------------------------------------------------------

# PART A --- PRODUCT VISION

Trigger Point is an evidence-first GTM operating system. It must help a company
decide who to sell to, why those buyers may need the product now, how to
reach them, what happened, and what to improve next.

The user provides a company website and a business goal. Trigger Point studies
the business. It asks only the questions that it cannot answer with
reliable evidence. It builds a versioned GTM strategy. It executes
approved tasks through connected tools. It records outcomes. It uses
verified outcomes to propose improvements.

Claude Office is the live control room. Claude Code is the execution
harness for the current build and local agent workflow. Trigger Point's backend
owns durable business state. MCP exposes typed tools. Hooks report
lifecycle events. The frontend must show actual state and actual events.
Do not simulate activity.

## Product principles

1.  Show evidence for important claims.
2.  Separate facts, user statements, assumptions, hypotheses, and
    recommendations.
3.  Store source URLs, event dates, retrieval dates, excerpts, and
    confidence.
4.  Ask a question only when its answer can change a decision.
5.  Use the simplest GTM motion that fits the business.
6.  Keep humans in control of consequential external actions.
7.  Make strategy changes visible and reversible.
8.  Learn from outcomes. Do not silently rewrite strategy based on one
    noisy result.
9.  Keep a full audit trail for tools, tasks, decisions, costs, and
    approvals.
10. Never claim that an integration works until it passes a real test.

# PART B --- END-TO-END GTM CHECKLIST

Use this list as the target product workflow. During the audit, mark
each item as `WORKING`, `PARTIAL`, `MISSING`, `BROKEN`, or
`NOT_APPLICABLE`. Include file paths, test evidence, and runtime
evidence.

## 1. Business intake and adaptive discovery

-   [ ] Accept the company website, product description, target
    geography, growth goal, and time horizon.
-   [ ] Read the website and identify products, features, audience,
    claims, pricing, use cases, proof, and calls to action.
-   [ ] Record the URLs and excerpts that support extracted facts.
-   [ ] Identify missing information and contradictions.
-   [ ] Ask a short, adaptive question set. Do not ask for facts that
    reliable sources already provide.
-   [ ] Ask about business model, stage, sales capacity, average
    contract value, sales cycle, current customers, alternatives,
    differentiation, budget, and constraints only when relevant.
-   [ ] Support user corrections and preserve the original answer and
    correction history.
-   [ ] Create an approved business profile and a source-of-truth
    record.
-   [ ] Show which facts came from the website, user, connected tools,
    or model inference.

## 2. Market and category research

-   [ ] Define the market category and adjacent categories.
-   [ ] Identify direct competitors, indirect competitors, substitutes,
    and the status quo.
-   [ ] Research comparable startups and successful GTM approaches in
    the same category or adjacent markets.
-   [ ] Search primary sources first: company websites, product pages,
    pricing pages, public case studies, founder interviews, public
    launch material, and customer stories.
-   [ ] Use secondary sources to find context and then verify key claims
    against primary sources where possible.
-   [ ] Record each source, publication date, event date, retrieval
    time, excerpt, and relevance.
-   [ ] Separate observed competitor facts from inferred strategy.
-   [ ] Extract positioning, target segment, pricing model, proof
    points, distribution channels, sales motion, onboarding,
    partnerships, and public growth tactics.
-   [ ] Do not infer private conversion rates, revenue, or outreach
    methods without evidence.
-   [ ] Produce a competitor map, market gaps, differentiation
    hypotheses, and unanswered questions.
-   [ ] Keep research fresh. Re-check time-sensitive facts before
    acting.

## 3. ICP creation: account-level fit

Build the ICP from evidence. Do not produce one generic persona and call
it an ICP.

-   [ ] Start with current customers, CRM data, wins, losses, retention,
    product usage, and customer interviews when available.
-   [ ] If customer data is missing, mark the ICP as a hypothesis and
    use market research. Do not invent customer evidence.
-   [ ] Define distinct segments when different segments have different
    needs, buying processes, value, or sales motions.
-   [ ] Record positive-fit criteria and explicit disqualifiers.
-   [ ] Evaluate the following dimensions where relevant:
    -   Firmographic: industry, sub-industry, employee range, revenue
        range, geography, business model, ownership, growth stage.
    -   Operational: workflow, process maturity, team structure, scale,
        complexity, and cost of the current process.
    -   Problem: pain severity, frequency, affected teams, cost of
        inaction, urgency, and current workaround.
    -   Value: measurable outcome, economic impact, time to value,
        strategic importance, and ability to realize value.
    -   Budget: budget owner, budget availability, purchasing power,
        budget cycle, and willingness to pay.
    -   Technographic: current tools, stack, integrations, competitor
        products, migration barriers, and technical fit.
    -   Readiness: active initiative, executive attention, internal
        champion, project timeline, change capacity, and implementation
        ability.
    -   Buying process: procurement, legal, security, compliance,
        approval steps, typical stakeholders, and likely sales-cycle
        length.
    -   Reachability: reliable company identity, relevant public
        business contact data, allowed channels, and practical ability
        to contact.
    -   Economics: expected contract value, acquisition effort,
        implementation cost, gross margin, expansion potential,
        retention potential, and service burden.
-   [ ] Separate must-have criteria from weighted preferences.
-   [ ] Set score definitions and weights. Explain why each criterion
    matters.
-   [ ] Treat initial weights as hypotheses until calibrated against
    actual outcomes.
-   [ ] Store confidence and evidence for each criterion.
-   [ ] Include negative-fit patterns and reasons to exclude an account.
-   [ ] Show ICP version, date, author/source, changes, and rationale.
-   [ ] Allow a user to accept, edit, reject, or compare ICP versions.

## 4. Value proposition, positioning, and messaging

-   [ ] Define the target segment, buyer problem, current alternative,
    promised outcome, differentiation, proof, and reason to believe.
-   [ ] State the value proposition in customer language.
-   [ ] Map each product capability to a customer outcome. Do not
    confuse features with value.
-   [ ] Define positioning against alternatives and the status quo.
-   [ ] Define message pillars and supporting proof.
-   [ ] Create separate messaging for each relevant stakeholder and
    buying stage.
-   [ ] Create claims that are evidence-backed. Flag claims that require
    customer proof or legal review.
-   [ ] Define pricing and packaging hypotheses if the user asks for
    them or if they block GTM planning.
-   [ ] Show open assumptions and the tests that could validate them.

## 5. Buying committee and stakeholder profiles

The ICP identifies the account. Personas identify people in that
account. A deal can involve several people. Do not assume every deal has
the same committee.

-   [ ] Identify relevant roles for the product and sales motion.
-   [ ] Consider these roles where applicable:
    -   End user or practitioner.
    -   Champion or internal advocate.
    -   Functional owner.
    -   Economic buyer or budget owner.
    -   Executive sponsor.
    -   Technical evaluator or implementation owner.
    -   Security, privacy, legal, or compliance reviewer.
    -   Procurement or vendor management.
    -   Likely blocker or competing internal priority.
    -   Partner, consultant, or external influencer.
-   [ ] For each persona, define their desired outcome, pain, risk,
    success metrics, objections, influence, likely questions, evidence
    needs, and appropriate call to action.
-   [ ] Distinguish known people from inferred roles.
-   [ ] Verify names, titles, employer, and profile URLs before
    outreach.
-   [ ] Map relationships only when a source supports them.
-   [ ] Do not contact every role by default. Recommend a sequence based
    on deal context.
-   [ ] Define a different purpose and message for each person. Do not
    send the same message to all stakeholders.
-   [ ] Explain why each person is relevant to the account and the
    buying process.

## 6. Account discovery and identity resolution

-   [ ] Convert the approved ICP into searchable company criteria.
-   [ ] Use connected company/person search providers, including
    Crustdata when configured.
-   [ ] Deduplicate accounts by canonical company identity and domain.
-   [ ] Resolve subsidiaries, parent companies, brands, and regional
    entities.
-   [ ] Store provider IDs, canonical domain, company name, geography,
    source, and last-verified date.
-   [ ] Exclude accounts that fail must-have criteria.
-   [ ] Score account fit separately from timing, evidence quality, and
    contactability.
-   [ ] Explain score components and rejection reasons.
-   [ ] Show how many accounts were found, deduplicated, qualified,
    rejected, and awaiting research.
-   [ ] Respect provider limits, licensing, access permissions, and
    data-retention rules.

## 7. Buying signals and account research

-   [ ] Search for signals that are relevant to the product and ICP.
-   [ ] Signal examples include funding, hiring, expansion, leadership
    changes, new locations, product launches, strategic initiatives,
    technology adoption, regulatory changes, contract events, and public
    statements about a problem.
-   [ ] Do not treat every signal as a buying signal. Explain the link
    between signal and customer need.
-   [ ] Store source URL, title, publisher, publication date, event
    date, retrieval timestamp, excerpt, associated entity, and
    verification status.
-   [ ] Distinguish event date from retrieval date.
-   [ ] Score signal relevance, freshness, strength, and source
    reliability separately.
-   [ ] Mark a signal as `VERIFIED`, `NEEDS_REVIEW`, `CONTRADICTED`, or
    `STALE`.
-   [ ] Do not invent sources, quotes, relationships, events, or dates.
-   [ ] Explain "Why this account?", "Why this person?", "Why now?", and
    "Why us?" with evidence.
-   [ ] Keep the case file for each account available in the office.

## 8. GTM motion, channel, and campaign planning

-   [ ] Recommend a motion that fits the business: founder-led sales,
    outbound, inbound, product-led growth, partnerships, community,
    content, events, channel sales, or a hybrid.
-   [ ] Explain why the motion fits the segment, deal size, buyer, sales
    cycle, and available resources.
-   [ ] Create a channel plan with audience, purpose, offer, timing,
    owner, cost, and success metric.
-   [ ] Support email, professional social networks, phone, events,
    partner introductions, content, and other configured channels.
-   [ ] Use only channels that have a real integration or a clearly
    labelled manual workflow.
-   [ ] Create account-specific and persona-specific message drafts.
-   [ ] Personalize with verified context. Do not fabricate familiarity
    or claim the prospect did something unless a source proves it.
-   [ ] Create sequences with stop rules, reply handling, suppression,
    opt-out handling, and duplicate prevention.
-   [ ] Define experiment hypotheses, variants, sample sizes where
    appropriate, metrics, and decision rules.
-   [ ] Require human approval before sending external messages or
    making external changes.
-   [ ] Keep drafts separate from scheduled, sent, delivered, replied,
    and booked states.
-   [ ] Show scheduled time, timezone, channel, recipient, sequence
    step, provider status, and delivery errors.

## 9. Meeting and customer feedback loop

-   [ ] Integrate Wispr Flow MCP when available and authorized.
-   [ ] Verify the real connection and read permissions. Wispr Flow MCP
    is a read-only source; do not assume it can create or modify notes.
-   [ ] Match a meeting to the right account, people, opportunity, and
    campaign using verified identifiers.
-   [ ] Import permitted notes, summaries, transcripts, attendees, and
    action items.
-   [ ] Extract pain points, desired outcomes, objections, alternatives,
    budget, urgency, buying process, success criteria, commitments, and
    next steps.
-   [ ] Preserve source links and transcript/note references where
    available.
-   [ ] Separate direct statements from model interpretation.
-   [ ] Mark missing or ambiguous details for review.
-   [ ] Update CRM or internal records only through a connected
    write-capable integration and only under the configured approval
    policy.
-   [ ] Connect meeting insights to the ICP, messaging, opportunity, and
    campaign version that produced the meeting.
-   [ ] Track whether the meeting progressed, stalled, or disqualified
    the account.

## 10. Self-improvement and organizational learning

Build a controlled learning loop. Do not let the model silently rewrite
its own rules or strategy.

-   [ ] Store durable, versioned memory for business facts, customer
    insights, campaign outcomes, tested tactics, and lessons.
-   [ ] Keep raw events and evidence separate from summarized memory.
-   [ ] Use retrieval to bring relevant lessons into each new mission.
-   [ ] Record each hypothesis, prediction, experiment, observed
    outcome, confidence, and decision.
-   [ ] Compare outcomes by segment, persona, signal, channel, message,
    offer, and timing.
-   [ ] Distinguish correlation from causation. Do not declare a tactic
    successful from one reply or one meeting.
-   [ ] Detect small samples, selection bias, attribution gaps, and
    delayed outcomes.
-   [ ] Propose changes to ICP weights, messaging, qualification rules,
    or channel allocation.
-   [ ] Show the evidence behind each proposed change.
-   [ ] Keep an approval gate for material strategy changes.
-   [ ] Version every approved change. Keep prior versions and allow
    rollback.
-   [ ] Evaluate changes against a baseline or holdout where practical.
-   [ ] Track whether the change improved qualified meetings,
    opportunity creation, conversion, sales cycle, retention, or unit
    economics.
-   [ ] Never learn from unverified synthetic fixture data as if it were
    a real customer outcome.
-   [ ] Allow users to inspect, correct, approve, or delete stored
    business memory.

## 11. Pipeline, meetings, and CRM

-   [ ] Define pipeline stages and entry/exit criteria.
-   [ ] Track account, contact, campaign, activity, meeting,
    opportunity, proposal, closed-won, closed-lost, and renewal
    relationships.
-   [ ] Track meeting booked, meeting held, qualified meeting,
    opportunity created, pipeline value, win/loss, and reason.
-   [ ] Track follow-up commitments and due dates.
-   [ ] Deduplicate activity across integrations.
-   [ ] Separate provider events from inferred CRM status.
-   [ ] Show next action and owner for each active opportunity.
-   [ ] Reconcile campaign attribution and flag uncertainty.

## 12. Finance and unit economics

-   [ ] Track spend by provider, channel, campaign, account, and period.
-   [ ] Track model/token spend, data-provider spend, enrichment
    credits, email infrastructure, paid media, events, tools, and other
    configured costs.
-   [ ] Record currency, source, date, whether a cost is actual or
    estimated, and whether it is recurring or one-time.
-   [ ] Show budget, actual spend, forecast spend, and variance.
-   [ ] Track cost per account researched, contact enriched, message
    sent, reply, qualified meeting, opportunity, and customer where data
    exists.
-   [ ] Track pipeline generated, revenue won, gross margin, CAC,
    payback, and ROI when the data supports these metrics.
-   [ ] Define attribution windows and formulas. Show missing data.
-   [ ] Never present pipeline as revenue or estimated spend as actual
    spend.
-   [ ] Make every finance metric traceable to source records and
    calculation logic.

## 13. GTM Office interface and observability

-   [ ] Show the live mission, strategy, ICP versions, target accounts,
    stakeholders, signals, campaigns, meetings, pipeline, experiments,
    and finance.
-   [ ] Clicking an agent shows its real task, current state, inputs,
    tool calls, outputs, evidence, errors, and retry history.
-   [ ] Show the full task timeline and event feed.
-   [ ] Show which work is running in Claude Code, which is running in a
    backend worker, and which is waiting for user input.
-   [ ] Show integration health and last successful sync for every
    provider.
-   [ ] Show `Idle`, `Running`, `Waiting for input`,
    `Waiting for approval`, `Succeeded`, `Failed`, and
    `Connection lost`.
-   [ ] Never use fake progress or simulated tool activity in live mode.
-   [ ] Clearly label fixture/demo mode.
-   [ ] Persist state so a refresh or restart does not erase missions.
-   [ ] Show source evidence next to recommendations.
-   [ ] Show strategy and ICP version history in a timeline.
-   [ ] Provide useful empty, loading, error, retry, disconnected, and
    permission-denied states.
-   [ ] Make all important changes auditable.

# PART C --- CORRECT CLAUDE CODE ARCHITECTURE

Audit the current repository before selecting an implementation. Do not
assume that every component below is already present.

## Responsibilities

-   **Claude Code harness:** executes the development-time or local
    agent workflow, invokes tools, and coordinates supported subagents.
-   **Trigger Point application core:** owns GTM domain logic, mission state,
    scores, evidence, business rules, approvals, and outcome records.
-   **MCP server:** exposes narrow, typed tools for Trigger Point capabilities
    to Claude Code.
-   **Claude Code hooks:** report lifecycle events and enforce
    deterministic controls where appropriate.
-   **Background job runner:** handles long-running or scheduled work if
    the current product architecture needs it.
-   **Database/event log:** persists state, events, artifacts, source
    evidence, approvals, and version history.
-   **Claude Office backend:** validates incoming events, provides task
    and mission APIs, and broadcasts updates to the frontend.
-   **Frontend:** renders the authoritative state and event stream. It
    does not invent agent progress.
-   **External connectors:** Crustdata, Wispr Flow, CRM, email,
    calendar, web research, and finance providers. Each connector must
    declare its capabilities and limits.

## Use each Claude Code mechanism for the right job

-   Use `CLAUDE.md` for concise project context, architecture pointers,
    and essential commands.
-   Use `.claude/rules/` for path-scoped constraints.
-   Use skills for repeatable GTM procedures, research protocols, review
    checklists, and quality gates.
-   Use subagents for bounded specialist work that can run independently
    and return structured results.
-   Use MCP for typed access to external data and Trigger Point actions.
-   Use hooks for deterministic lifecycle telemetry and controls.
-   Use ordinary application code for durable state, queues, retries,
    scoring, validation, event persistence, and approval enforcement.
-   Use a shared event schema to connect the runtime to the office.
-   Do not treat Claude Code hooks as a durable workflow engine or
    database.
-   Do not rely on a prompt alone to enforce safety. Enforce critical
    rules in code, permissions, and tests.
-   Inspect the current Claude Code documentation and the installed CLI
    version before coding. Do not guess hook event names or payload
    schemas.

## Suggested MCP tool groups

Create only tools that the current workflow needs. Keep tools narrow,
typed, documented, and testable.

1.  **Mission:** `create_mission`, `get_mission`, `update_mission`,
    `cancel_mission`.
2.  **Business profile:** `extract_business_profile`,
    `get_business_profile`, `approve_business_profile`.
3.  **Strategy:** `research_market`, `build_icp`,
    `compare_icp_versions`, `draft_positioning`, `propose_gtm_plan`.
4.  **Accounts:** `discover_accounts`, `resolve_company_identity`,
    `score_account`, `get_account_case_file`.
5.  **People:** `find_stakeholders`, `verify_person`,
    `map_buying_committee`.
6.  **Signals and evidence:** `research_signals`, `verify_evidence`,
    `get_source_record`.
7.  **Campaigns:** `draft_campaign`, `validate_campaign`,
    `request_campaign_approval`, `schedule_approved_campaign` only if a
    real scheduling connector exists.
8.  **Meetings and learning:** `search_meetings`, `get_meeting_notes`,
    `extract_meeting_insights`, `propose_strategy_update`,
    `approve_strategy_update`.
9.  **Metrics:** `get_pipeline_metrics`, `get_campaign_metrics`,
    `get_cost_metrics`, `get_learning_history`.
10. **Office state:** `get_mission_status`, `get_agent_task`,
    `get_event_history`, `get_integration_health`.

Return structured output. Include stable IDs, status, source references,
timestamps, and errors. Do not return large raw transcripts by default
when a bounded summary and source reference will work.

## Event design

Inspect the existing Claude Office event schema before changing it.
Reuse it if it is sound. Otherwise, propose a migration.

Use events such as: `mission.created`, `mission.updated`, `task.queued`,
`task.started`, `agent.started`, `tool.started`, `tool.completed`,
`evidence.created`, `approval.requested`, `approval.resolved`,
`task.failed`, `task.retrying`, `task.completed`, `strategy.versioned`,
`integration.health_changed`, `meeting.imported`, `outcome.recorded`,
`mission.completed`.

Each event should have: - `event_id` - `mission_id` - `task_id` when
relevant - `agent_id` when relevant - `event_type` - `occurred_at` -
`recorded_at` - `status` - `correlation_id` - `summary` - `artifact_ids`
or source references - `schema_version`

Support idempotency, ordering, reconnect/replay, redaction, and error
reporting. Do not put secrets, access tokens, or full sensitive
transcripts in the event feed.

# PART D --- REQUIRED AUDIT METHOD

You are Claude Code working in the user's existing Trigger Point repository and
cloned Claude Office repository.

**This task starts in AUDIT MODE. Do not make broad code changes until
you complete the audit and present the findings.** You may run read-only
inspection commands and existing tests. Do not overwrite user changes.
Do not expose secrets.

## Step 1 --- Establish repository reality

1.  Print the current working directory and Git status for each
    repository.
2.  Inspect the project structure, package manifests, `CLAUDE.md`,
    `.claude/`, MCP configuration, hooks, server, frontend, database
    models, migrations, job runners, tests, and docs.
3.  Inspect recent Git history and uncommitted changes.
4.  Identify which repository owns each feature.
5.  Run the existing lint, type-check, unit tests, integration tests,
    and build where feasible.
6.  Record command, result, and any environment blocker.
7.  Do not say that a feature works because a file exists. Find a test
    or run the feature.

## Step 2 --- Audit the Claude Code harness

Check: - Claude Code CLI version and supported hook schema. - Configured
MCP servers and whether each connects. - Tool names, schemas,
permissions, timeouts, errors, and provider dependencies. - `CLAUDE.md`,
rules, skills, and subagents. Check for duplicate, conflicting, or
oversized instructions. - Hook event names, handlers, payload
validation, failure behavior, timeouts, and security. - Whether the code
invokes Claude Code through a supported harness or merely calls a model
API. - Whether a mission can survive a long run, context compaction,
tool error, process restart, and user cancellation. - Whether external
actions are approval-gated in code. - Whether costs and run IDs are
recorded. - Whether prompt versions and tool versions are traceable.

## Step 3 --- Audit Claude Office integration

Check: - How Claude Office receives events. - How hooks or other runtime
components send events. - Whether the server validates the payload and
authenticates the sender. - Whether WebSocket updates are real and
correctly ordered. - Whether task state persists in a database or only
in memory. - Whether page refresh and reconnect restore the mission. -
Whether selecting an agent displays its real task and artifacts. -
Whether errors, retries, approvals, idle state, and disconnection are
visible. - Whether the frontend uses actual backend state or
hard-coded/demo data. - Whether live and fixture modes are clearly
separated. - Whether logs and events expose secrets or sensitive data.

## Step 4 --- Audit GTM domain functionality

For every checklist item in Part B, assign exactly one status: -
`WORKING`: demonstrated by a passing test or reproducible runtime
evidence. - `PARTIAL`: some behavior exists, but important requirements
are missing. - `MISSING`: no implementation found. - `BROKEN`:
implementation exists but a test or runtime check failed. -
`NOT_APPLICABLE`: explain why.

For each item, include: - evidence and file paths; - test or command
used; - what the user can currently do; - missing behavior; - severity:
`P0`, `P1`, `P2`, or `P3`; - estimated implementation effort as a range,
not false precision.

Audit ICP, multi-persona mapping, evidence, account identity, buying
signals, competitor research, channel planning, campaign drafts,
approvals, Wispr Flow, learning, CRM, finance, office visibility, and
reporting separately.

## Step 5 --- Audit integrations

For each integration, report: - connector name and purpose; - configured
/ missing / unauthorized / failed / untested; - tools exposed and their
schemas; - read/write capabilities; - last successful test; - required
environment variable names, never their values; - rate limits, cost,
data access, retention, and known constraints; - safe failure
behavior; - fixture mode availability.

At minimum inspect Crustdata, web research, Wispr Flow MCP, any
email/calendar/CRM integrations, finance sources, and the Claude Office
event connection. Do not claim that Wispr Flow is connected unless a
real test reads an expected meeting. Its documented MCP is read-only. Do
not assume write capability.

## Step 6 --- Audit prompts and agent quality

Find all system prompts, task templates, skills, subagent instructions,
schemas, scoring rules, and validators.

For each one, report: - purpose and caller; - input schema and output
schema; - source-grounding requirements; - failure and retry behavior; -
examples and evaluation tests; - duplication or conflict with other
instructions; - prompt/version history; - whether it asks for
unsupported claims; - whether output is validated by deterministic code.

Create or recommend an evaluation set for: - correct ICP extraction; -
separation of ICP and persona; - correct stakeholder roles; - source
quality and event-date extraction; - unsupported-claim rejection; -
duplicate account resolution; - useful signal relevance; - accurate "Why
this account/person/now/us?" explanations; - personalized but factual
messages; - meeting insight extraction; - correct learning
recommendations; - finance calculations and attribution.

Use known-good, edge-case, contradictory, stale-source, and empty-result
cases. Measure quality with explicit rubrics. Do not optimize prompts
only for length or style. Optimize for accuracy, evidence, useful
decisions, and reproducible behavior.

## Step 7 --- Audit the self-improvement loop

Trace the actual path from an outcome to a future decision.

Check whether the product stores: - raw activity and source evidence; -
meeting insights and user corrections; - campaign, account, and
opportunity outcomes; - hypotheses and experiment definitions; -
proposed strategy changes; - approval decisions; - versioned strategy,
ICP, and messaging; - measured results after a change.

Identify where this chain stops. A memory file alone is not a GTM
learning system.

Recommend a controlled learning process: 1. Capture a verified event or
user correction. 2. Link it to the account, segment, persona, campaign,
strategy version, and outcome. 3. Extract a candidate lesson with
supporting evidence. 4. Check sample size, data quality, contradictions,
and alternative explanations. 5. Propose a specific change. 6. Ask for
approval when the change affects strategy or external actions. 7.
Version the approved change. 8. Measure results against a baseline or
experiment. 9. Keep or roll back the change based on evidence.

## Step 8 --- Produce the audit report before implementation

Create `docs/GTMO_AUDIT_REPORT.md` (or the existing equivalent) with: 1.
Executive summary. 2. Repository and runtime architecture. 3. Baseline
tests and failures. 4. Status matrix for every Part B checklist area. 5.
Evidence and file paths for every status. 6. MCP, hooks, subagents,
skills, prompts, and connector audit. 7. Claude Office event-to-frontend
trace. 8. GTM workflow gaps. 9. ICP and stakeholder-model gaps. 10.
Wispr Flow and meeting-learning gaps. 11. Self-improvement gaps. 12.
Finance and metrics gaps. 13. Security and approval gaps. 14.
Prioritized implementation roadmap. 15. Proposed acceptance tests. 16.
Questions that require the user. Ask only questions that block a correct
decision.

Also create or update `docs/GTMO_IMPLEMENTATION_ROADMAP.md` with small,
testable phases.

Do not report a guessed status. Use `UNVERIFIED` where evidence is not
available, and explain what test is needed.

# PART E --- IMPLEMENTATION ORDER AFTER AUDIT APPROVAL

Do not attempt to build every feature in one change. Implement and test
one complete vertical slice at a time.

## Phase 1 --- Runtime and office truth

-   Establish the authoritative mission/task state.
-   Connect the real execution runtime to the office event stream.
-   Show task status, tool activity, artifacts, errors, approvals, and
    reconnect state.
-   Remove fake progress from live mode.
-   Add end-to-end tests.

## Phase 2 --- Business profile and strategy foundation

-   Implement website extraction and source grounding.
-   Add adaptive clarification questions.
-   Create the business profile, value proposition, market map, and
    versioned GTM plan.
-   Add user review and edits.

## Phase 3 --- ICP and account discovery

-   Build segment-specific ICP schemas and fit/exclusion rules.
-   Add explainable deterministic scoring.
-   Connect Crustdata and validate company identity.
-   Show account scores, source evidence, and rejection reasons.

## Phase 4 --- Stakeholders, signals, and account case files

-   Map relevant buying roles.
-   Find and verify people.
-   Research and score timing signals.
-   Generate evidence-backed account case files.

## Phase 5 --- Campaign planning and approvals

-   Draft persona-specific outreach.
-   Add channel, sequence, timing, and experiment plans.
-   Add approval, suppression, opt-out, and duplicate checks.
-   Keep sends disabled until a real connector and safe approval flow
    pass tests.

## Phase 6 --- Meetings and feedback

-   Connect Wispr Flow MCP using its documented read-only capability.
-   Import meeting insights and link them to accounts and campaigns.
-   Capture outcomes, objections, corrections, and next steps.

## Phase 7 --- Learning and strategy evolution

-   Version ICP, positioning, messaging, and experiments.
-   Propose improvements from verified outcomes.
-   Add approval, comparison, and rollback.
-   Show the learning timeline and why each version changed.

## Phase 8 --- Pipeline and finance

-   Connect CRM and channel data where available.
-   Reconcile meetings, opportunities, revenue, and spend.
-   Label actual, estimated, attributed, and missing values separately.
-   Add formula tests and data-quality warnings.

## Phase 9 --- Demo hardening

-   Add seeded fixture data with a clear `DEMO MODE` label.
-   Add a live mode that uses real connected services.
-   Test empty, slow, failed, unauthorized, and disconnected
    integrations.
-   Verify every screen and click path.
-   Update setup instructions and reproduce the demo from a clean start.

# PART F --- DEFINITION OF DONE

Do not declare the system complete unless all applicable checks pass.

-   [ ] The audit report distinguishes verified behavior from
    assumptions.
-   [ ] A real website and goal create a persistent mission.
-   [ ] The user can review and approve the business profile and GTM
    strategy.
-   [ ] The ICP contains evidence, fit criteria, exclusions, and version
    history.
-   [ ] Account discovery and person mapping use real providers when
    configured.
-   [ ] Buying signals include verified source records and event dates.
-   [ ] Each account has an explainable fit score and a source-backed
    case file.
-   [ ] Each stakeholder has a role-specific purpose and message.
-   [ ] Campaign drafts, scheduled messages, and sent messages are
    different states.
-   [ ] No external send or write happens without the required approval.
-   [ ] Wispr Flow meeting insights can be traced to the meeting source
    and related account.
-   [ ] The system can propose a strategy change and show the evidence
    behind it.
-   [ ] Approved changes create a new version and preserve the prior
    version.
-   [ ] Finance metrics have tested formulas and visible data
    limitations.
-   [ ] Claude Office displays real mission and agent activity.
-   [ ] Refresh and reconnect preserve the mission and event history.
-   [ ] Live mode and fixture mode are distinct.
-   [ ] Errors, retries, integration health, and permission waits are
    visible.
-   [ ] Relevant unit, integration, and end-to-end tests pass.
-   [ ] Documentation explains setup, environment variable names,
    limitations, and demo steps.

# PART G --- FINAL INSTRUCTION TO CLAUDE CODE

Start in audit mode. Inspect the repositories and current runtime. Run
the existing checks. Trace one user request from the frontend through
Claude Code, MCP tools, Trigger Point logic, external providers, persisted
state, events, and the Claude Office UI.

Produce the audit report and prioritized roadmap first. Do not make
large changes before reporting what exists, what works, what is partial,
and what is missing.

After the audit, recommend the smallest high-value vertical slice. Wait
for the user to approve the implementation plan before making broad
architectural changes. Preserve user changes and secrets. Test every
change. Report exact commands and results.

# RESEARCH REFERENCES

Use current official documentation and verify it against the installed
versions.

-   Claude Code best practices:
    https://code.claude.com/docs/en/best-practices
-   Claude Code hooks: https://code.claude.com/docs/en/hooks-guide
-   Claude Code MCP: https://code.claude.com/docs/en/mcp
-   Claude Code subagents: https://code.claude.com/docs/en/sub-agents
-   Claude Code skills: https://code.claude.com/docs/en/skills
-   Claude guidance on hooks, skills, rules, and subagents:
    https://claude.com/resources/articles/steering-claude-code-skills-hooks-rules-subagents-and-more
-   HubSpot ICP template and methodology:
    https://www.hubspot.com/make-my-persona/ideal-customer-profile-template
-   HubSpot buyer persona research:
    https://blog.hubspot.com/marketing/buyer-persona-research
-   Salesforce GTM strategy playbook:
    https://www.salesforce.com/blog/gtm-strategy-framework-playbook/
-   Wispr Flow MCP setup and capabilities:
    https://docs.wisprflow.ai/articles/9551372685-connect-an-mcp-client-to-wispr-flow-remote-mcp-server
-   Hermes Agent memory and learning patterns:
    https://hermes-agent.nousresearch.com/docs/user-guide/features/memory

Important: Hermes is a reference for curated memory and reviewable
learning patterns. Do not copy its memory design blindly. Trigger Point must
learn from account, campaign, meeting, pipeline, and revenue outcomes,
not only conversational history.
