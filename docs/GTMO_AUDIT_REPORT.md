# Trigger Point GTM OS Audit Report

_Current truth, measured against `docs/GTM_OS_PRODUCT_SPEC.md`. A status changes only with a test or a real run._

## 1. Executive summary
Trigger Point runs one complete path under real Claude Code from the Office: website, sourced profile, strategy, versioned ICP, accounts, signals, a buyer, a case file, verified outreach, hash-bound approval, and a test send and meeting. What comes back feeds a closed loop: replies and meetings become reviewed insights, then lessons, then a versioned change that future work receives and that is measured against a holdout.

- **Score:** of 138 checklist items, 66 are working, 53 partial, 19 missing, 0 broken, 0 unverified and 0 not applicable.
- **Biggest blocker:** finding a "why now" for Indian schools. Live discovery returns real Mumbai schools, but Crustdata holds no job postings for them, so each is rejected with `no_fresh_why_now`. Case files and drafts on live accounts stay unproven until a real signal exists.
- **Biggest missing area:** outside market research.
- **The loop has not run on real results.** It is proven end to end on labelled fixture data. Test sends never teach, so it needs real sends you log or real meetings.
- **Email:** real sends work, to the test inbox only. Mail from a consumer Gmail account landed in spam, so real outreach needs an authenticated sending domain first.

## 2. Repository and runtime architecture
| Layer | Location | Reality |
|---|---|---|
| Claude Code harness | `.claude/` | 8 agents, 3 skills, project hooks |
| Trigger Point core | `src/trigger_point` | Python 3.12. State machine, scoring, evidence, approvals |
| MCP server | `src/trigger_point/mcp_server.py`, `workflow/mcp_tools.py` | stdio, 36 tools, 6 ask-gated. No tool can approve learning |
| Persistence | SQLite | `trigger_point.db`; `wf_events` is the event log |
| Office backend | `src/trigger_point/office` | FastAPI, token auth, held approvals, live ticks |
| Office UI | `office/` | React and Vite, built from scratch |
| Mission Runner | `src/trigger_point/office/runner.py` | Starts and resumes the Director from the Office |
| LLM | Hyde GLM 5.3 Flash | Structured extraction, strategy, ICP and drafts. Claude runs the workflow |
| Scheduler | `src/trigger_point/office/scheduler.py` | Runs while the Office runs. Asks the Director when a send is due |

## 3. Status matrix
| Area | Items | WORKING | PARTIAL | MISSING | BROKEN | UNVERIFIED | N/A |
|---|---|---|---|---|---|---|---|
| 1. Business intake and adaptive discovery | 9 | 4 | 4 | 1 | 0 | 0 | 0 |
| 2. Market and category research | 11 | 1 | 4 | 6 | 0 | 0 | 0 |
| 3. ICP creation: account-level fit | 12 | 5 | 5 | 2 | 0 | 0 | 0 |
| 4. Value proposition, positioning, and messaging | 9 | 7 | 1 | 1 | 0 | 0 | 0 |
| 5. Buying committee and stakeholder profiles | 9 | 1 | 7 | 1 | 0 | 0 | 0 |
| 6. Account discovery and identity resolution | 10 | 7 | 2 | 1 | 0 | 0 | 0 |
| 7. Buying signals and account research | 10 | 4 | 6 | 0 | 0 | 0 | 0 |
| 8. GTM motion, channel, and campaign planning | 12 | 11 | 1 | 0 | 0 | 0 | 0 |
| 9. Meeting and customer feedback loop | 11 | 7 | 3 | 1 | 0 | 0 | 0 |
| 10. Self-improvement and organizational learning | 15 | 12 | 3 | 0 | 0 | 0 | 0 |
| 11. Pipeline, meetings, and CRM | 8 | 1 | 4 | 3 | 0 | 0 | 0 |
| 12. Finance and unit economics | 9 | 1 | 5 | 3 | 0 | 0 | 0 |
| 13. GTM Office interface and observability | 13 | 5 | 8 | 0 | 0 | 0 | 0 |
| **Total** | **138** | **66** | **53** | **19** | **0** | **0** | **0** |

## 4. Evidence for every item
Effort: S under 1 day, M 1 to 3 days, L 3 to 10 days, XL 2 weeks or more. These are ranges, not commitments.

### 1. Business intake and adaptive discovery

| Item | Status | Sev | Effort | Evidence | Missing |
|---|---|---|---|---|---|
| Accept website, product description, geography, growth goal, time horizon | WORKING | - | - | `IntakeBrief`; `tests/context/test_intake_honesty.py`; New mission form. | - |
| Read site; find products, features, audience, claims, pricing, use cases, proof, CTAs | PARTIAL | P0 | L | `web/crawl.py`, `web/extract.py`, `context/service.py`. Sitemaps and streamed React pages are read (`tests/web/test_streamed_pages.py`). Unreadable or thin sites are flagged. | Purely client-rendered sites. Pricing and CTA fields. |
| Record URLs and excerpts for facts | WORKING | - | - | `context/grounding.py`; `tests/context/test_grounding.py` (quote must exist verbatim). | - |
| Identify missing information and contradictions | PARTIAL | P2 | M | `unknowns` list. Thin-site trace surfaced unknowns. | No contradiction detection. |
| Short, adaptive question set | PARTIAL | P1 | M | `clarification_questions`, max 3. The Director asks them in Office chat. | Answers are free text, with no typed path. |
| Ask about model, stage, capacity, ACV, cycle, customers, budget only when relevant | MISSING | P2 | M | No structured fields. The LLM may ask, unguided. | Typed business-facts schema and question policy. |
| Support corrections; preserve original and history | WORKING | - | - | Append-only versions; `test_edit_then_approve_versions_and_preserves_machine_draft`; profile page edits. | - |
| Approved business profile as source of truth | WORKING | - | - | A profile with no supported or user-provided facts cannot be approved: `test_empty_profile_cannot_be_approved`. | - |
| Show which facts came from website, user, tools or inference | PARTIAL | P1 | M | `ClaimKind`: fact, inference, user_provided. Spec needs facts, user statements, assumptions, hypotheses, recommendations. | Connected-tool origin; wider claim classes; display in Office. |

### 2. Market and category research

| Item | Status | Sev | Effort | Evidence | Missing |
|---|---|---|---|---|---|
| Define market category and adjacent categories | PARTIAL | P2 | L | `workflow/strategy.py` market map, from the approved profile and the model. | Sourced outside research. |
| Identify direct, indirect competitors, substitutes, status quo | PARTIAL | P2 | L | Strategy market map lists alternatives, labelled as hypotheses. | Sourced outside research. |
| Research comparable startups and GTM approaches | MISSING | P2 | XL | No outside research connector. | Web research connector. |
| Search primary sources first | MISSING | P2 | L | No outside research connector. | Source-tier policy. |
| Verify secondary sources against primary | MISSING | P2 | L | No outside research connector. | Verification step. |
| Record source, publication and event date, retrieval, excerpt, relevance | MISSING | P2 | M | No outside research connector. | Extend `Evidence` with publication date, title and relevance. |
| Separate observed competitor facts from inferred strategy | WORKING | - | - | `workflow/strategy.py` labels observed facts apart from inference, checked in code. | - |
| Extract positioning, segment, pricing, proof, channels, motion, onboarding, partnerships, tactics | MISSING | P2 | L | No outside research connector. | Competitor record schema. |
| Do not infer private conversion, revenue or outreach | PARTIAL | P2 | M | Prompt rule in `workflow/strategy.py`. | A validator. |
| Produce competitor map, gaps, differentiation hypotheses, questions | PARTIAL | P2 | L | Strategy page shows gaps and differentiation hypotheses. | Sourced outside research. |
| Re-check time-sensitive facts before acting | MISSING | P2 | M | No outside research connector. | Recheck job. |

### 3. ICP creation: account-level fit

| Item | Status | Sev | Effort | Evidence | Missing |
|---|---|---|---|---|---|
| Start from customers, CRM, wins, losses, retention, usage, interviews | MISSING | P2 | XL | No customer-data input. | Depends on CRM, meetings. |
| Without customer data, mark ICP as hypothesis | WORKING | - | - | Every ICP version is labelled hypothesis; `tests/workflow/test_icp.py`. | - |
| Define distinct segments | MISSING | P1 | L | One `GTMPlan` per mission. | Segment list. |
| Positive-fit criteria and explicit disqualifiers | WORKING | - | - | `workflow/icp.py`; `test_criteria_split_must_haves_preferences_and_disqualifiers`. | - |
| Evaluate all ten dimensions | PARTIAL | P1 | XL | Firmographic (size, geography) and technographic (keywords) only. Operational, problem, value, budget, readiness, buying process, reachability and economics are absent from the ICP. | Dimension schema with evidence. |
| Separate must-haves from weighted preferences | WORKING | - | - | Same test; ICP dashboard. | - |
| Set definitions and weights; explain each | PARTIAL | P2 | M | `WEIGHTS`, `Component.detail`; `tests/research/test_scoring.py`. | A reason for each criterion. |
| Treat weights as hypotheses until calibrated | PARTIAL | P2 | S | Stated in `research/scoring.py` docstring. | Visible label; calibration. |
| Store confidence and evidence per criterion | PARTIAL | P1 | L | Confidence and basis stored per criterion. | An evidence link per criterion. |
| Negative-fit patterns and exclusion reasons | WORKING | - | - | Disqualifiers carry reasons; same test. | - |
| Show ICP version, date, author, changes, rationale | WORKING | - | - | `IcpVersion`; `test_a_new_version_says_what_changed`; ICP page. | - |
| Accept, edit, reject or compare ICP versions | PARTIAL | P1 | L | Accept and reject via approval gate. | Edit and compare. |

### 4. Value proposition, positioning, and messaging

| Item | Status | Sev | Effort | Evidence | Missing |
|---|---|---|---|---|---|
| Define segment, problem, alternative, outcome, differentiation, proof | WORKING | - | - | Structured value proposition in `workflow/strategy.py`; Strategy page. | - |
| State value proposition in customer language | WORKING | - | - | Strategy record, checked against the approved profile. | - |
| Map capability to customer outcome | WORKING | - | - | Strategy record. | - |
| Position against alternatives and status quo | WORKING | - | - | Strategy record. | - |
| Define message pillars and proof | WORKING | - | - | Strategy record. | - |
| Separate messaging per stakeholder and stage | WORKING | - | - | Per audience: `workflow/outreach.py` `AUDIENCES`, each with a purpose and an ask; `tests/workflow/test_outreach.py`. Live messages for two audiences verified. | Per named person. |
| Evidence-backed claims; flag what needs proof or legal review | WORKING | - | - | `drafts/verifier.py`, `outreach-verifier-v1`; strategy marks claims that need proof. | - |
| Pricing and packaging hypotheses when needed | MISSING | P3 | M | Nothing. | Optional. |
| Show open assumptions and validating tests | PARTIAL | P2 | M | ICP assumptions only. | Linked experiments. |

### 5. Buying committee and stakeholder profiles

| Item | Status | Sev | Effort | Evidence | Missing |
|---|---|---|---|---|---|
| Identify relevant roles | PARTIAL | P1 | M | `GTMPlan.personas` with titles. | Role types. |
| Consider end user, champion, owner, economic buyer, sponsor, evaluator, reviewer, procurement, blocker, partner | PARTIAL | P1 | L | `test_stakeholder_role_from_title`; inferred from title and labelled so. | Roles from evidence, not only titles. |
| Per persona: outcome, pain, risk, metrics, objections, influence, questions, evidence, CTA | MISSING | P1 | L | Only `why`. | Persona profile model. |
| Distinguish known people from inferred roles | WORKING | - | - | Committee dashboard shows both, labelled. | - |
| Verify names, titles, employer, URLs | PARTIAL | P1 | M | Employer must equal the account id, `tests/research/test_people.py`. Fixture only. | Live proof; freshness recheck. |
| Map relationships only with a source | PARTIAL | P2 | M | No relationship data; every case says so. | Relationship records. |
| Do not contact every role; recommend a sequence | PARTIAL | P1 | M | Stakeholder view shows sequence, purpose and ask. | Multi-account logic on live data. |
| Different purpose and message per person | PARTIAL | P1 | L | Per audience, not per named person. | Per-person drafts. |
| Explain why each person matters | PARTIAL | P1 | M | `why_person` in case-v1, for the best person only. | All stakeholders. |

### 6. Account discovery and identity resolution

| Item | Status | Sev | Effort | Evidence | Missing |
|---|---|---|---|---|---|
| Convert approved ICP into search criteria | WORKING | - | - | `mission/compiler.py`; `tests/mission/test_compiler.py`; verified end to end on fixtures. | - |
| Use company and person providers, including Crustdata | WORKING | - | - | Live calls to identify, company, job and person search through the adapter; a full live mission ran through scoring. | - |
| Deduplicate by canonical identity and domain | WORKING | - | - | `mission/selection.py`; `test_replay_discovery_dedupes_excludes_and_receipts`. | - |
| Resolve subsidiaries, parents, brands, regional entities | MISSING | P2 | L | Domain and provider id only. | Hierarchy data. |
| Store provider IDs, domain, name, geography, source, last-verified | PARTIAL | P2 | S | `Company` fields; `provider_updated_at`. | No last-verified date of our own. |
| Exclude accounts failing must-haves | WORKING | - | - | `select_accounts`, hard rejections, tests. | - |
| Score fit separately from timing, evidence, contactability | WORKING | - | - | Four components in score-v1; `tests/research/test_scoring.py`. | - |
| Explain score components and rejection reasons | WORKING | - | - | `ScoreBreakdown`; Office shows every component. | - |
| Show found, deduplicated, qualified, rejected, awaiting research | WORKING | - | - | Funnel in the Accounts dashboard, from `DiscoveryRun` data. | - |
| Respect limits, licensing, access, retention | PARTIAL | P1 | M | Budget fails closed, rate-limit waits (`test_rate_limit_waits_for_reset_then_succeeds`). | No retention rules. |

### 7. Buying signals and account research

| Item | Status | Sev | Effort | Evidence | Missing |
|---|---|---|---|---|---|
| Search for product- and ICP-relevant signals | PARTIAL | P1 | L | Job postings, headcount and funding via `research/signals.py`, proven live. | Web and social sources. |
| Funding, hiring, expansion, leadership, launches, tech, regulation, statements | PARTIAL | P1 | L | Hiring, headcount and funding, proven live: `crustdata.com`'s real seed round was read with a correct date. | Expansion, leadership, launches, regulation, statements: need web or social search. |
| Explain the link between signal and need | PARTIAL | P2 | M | Case hypotheses labelled inference. | Per-signal rationale. |
| Store URL, title, publisher, publication and event dates, retrieval, excerpt, entity, status | PARTIAL | P1 | M | `Evidence` and `EvidenceRecord`. No title or publication date. | Two fields. |
| Distinguish event date from retrieval date | WORKING | - | - | `event_on`, `as_of`, `retrieved_at`; `test_no_date_is_undated_and_retrieval_time_never_stands_in`. | - |
| Score relevance, freshness, strength, reliability separately | PARTIAL | P2 | M | Strength and age decay. | Relevance and reliability. |
| Mark VERIFIED, NEEDS_REVIEW, CONTRADICTED or STALE | PARTIAL | P1 | S | audit-v1 uses verified, stale, undated, entity_mismatch, unverifiable. No contradiction check. | Align the vocabulary. |
| Do not invent sources, quotes, relationships, events, dates | WORKING | - | - | Grounding, verifier; live GLM drafts checked. | Audit-v1 cannot prove an excerpt says what is claimed. |
| Explain why account, person, now, us with evidence | WORKING | - | - | `cases/builder.py`; `tests/cases/test_case_builder.py`; rendered in Office, fixture data. | - |
| Keep the case file available in the office | WORKING | - | - | Evidence Auditor dashboard. | One account per mission only. |

### 8. GTM motion, channel, and campaign planning

| Item | Status | Sev | Effort | Evidence | Missing |
|---|---|---|---|---|---|
| Recommend a fitting motion | WORKING | - | - | Strategy record, labelled hypothesis. | - |
| Explain why the motion fits | WORKING | - | - | Strategy record. | - |
| Channel plan: audience, purpose, offer, timing, owner, cost, metric | WORKING | - | - | Strategy record; Strategy page. | - |
| Support email, social, phone, events, partners, content | PARTIAL | P2 | XL | Email draft only. | Other channels. |
| Only real integrations or labelled manual workflow | WORKING | - | - | Trigger Point MCP tools cannot send. Gmail and Calendar reach only `TRIGGER_POINT_TEST_RECIPIENTS`. Meetings, outcomes and costs are labelled manual. | - |
| Account- and persona-specific drafts | WORKING | - | - | Per target and audience; live on two audiences. | - |
| Personalize with verified context; no fake familiarity | WORKING | - | - | verifier-v1 (18 tests) rejects fake familiarity and past-relative time. | - |
| Sequences with stop rules, replies, suppression, opt-out, duplicates | WORKING | - | - | `write_follow_up`, three steps, stops on any answer; suppression and duplicate checks. | - |
| Experiment hypotheses, variants, samples, metrics, decision rules | WORKING | - | - | Each approved change runs with a variant, metric and decision rule. | - |
| Human approval before external messages or changes | WORKING | - | - | No Trigger Point tool sends (`test_no_tool_can_send_or_write_outward`); hash-bound approval; held calls proven by real clicks; the hook denies recipients outside the allowlist; a scheduled send is still held for a click. | - |
| Keep drafts separate from scheduled, sent, delivered, replied, booked | WORKING | - | - | `lifecycle`: each state needs its own proof. | - |
| Show schedule, timezone, channel, recipient, step, status, errors | WORKING | - | - | Outreach card shows time, timezone, channel, recipient, step, state and error. | - |

### 9. Meeting and customer feedback loop

| Item | Status | Sev | Effort | Evidence | Missing |
|---|---|---|---|---|---|
| Integrate Wispr Flow MCP when available and authorized | WORKING | - | - | Real tools read through Claude Code. A live transcript was captured by the hook and parsed by `workflow/loop.py`. | - |
| Verify real connection and read permissions | WORKING | - | - | `claude mcp list` drives the Integrations page; a real meeting was read. Wispr is read only. | - |
| Match a meeting to account, people, opportunity, campaign | PARTIAL | P1 | L | Calendar id or a target name in the record links it; anything else goes to the review queue. `tests/workflow/test_feedback.py`. | People and opportunity matching. |
| Import notes, summaries, transcripts, attendees, actions | WORKING | - | - | `import_meeting` reads the captured notes, summary and full transcript across cut-off parts. Attendees are stored when Wispr returns them. | - |
| Extract pains, outcomes, objections, budget, urgency, process, next steps | PARTIAL | P1 | L | `add_meeting_insights` with ten kinds; validated in code. | A full Director run on a real meeting. |
| Preserve source links and references | WORKING | - | - | Share link kept on each meeting and insight. | - |
| Separate direct statements from interpretation | WORKING | - | - | A statement needs a quote found verbatim in the captured source; an interpretation goes to review. | - |
| Mark missing or ambiguous details for review | WORKING | - | - | Review queue on the Meetings page: confirm, correct, reject. | - |
| Update CRM only via connected writer under policy | MISSING | P2 | L | Wispr Flow is not connected. | CRM connector. |
| Connect insights to ICP, messaging, opportunity, campaign version | PARTIAL | P1 | L | Meetings carry strategy and ICP versions; outcomes carry the message and version. | Opportunity link. |
| Track progressed, stalled, disqualified | WORKING | - | - | Progressed, stalled and disqualified on each imported meeting. | - |

### 10. Self-improvement and organizational learning

| Item | Status | Sev | Effort | Evidence | Missing |
|---|---|---|---|---|---|
| Durable versioned memory for facts, insights, outcomes, tactics, lessons | WORKING | - | - | Lessons with wording history, status, evidence and strategy version. | - |
| Keep raw events and evidence separate from summaries | WORKING | - | - | Raw captures are stored apart and never sent to the page. | - |
| Retrieve relevant lessons into a new mission | WORKING | - | - | `lessons_for`: approved lessons reach strategy, ICP and message prompts for that seller, across missions. | - |
| Record hypothesis, prediction, experiment, outcome, confidence, decision | PARTIAL | P1 | L | Strategy experiments and proposals record hypotheses. | Predictions and decisions per experiment. |
| Compare outcomes by segment, persona, signal, channel, message, offer, timing | PARTIAL | P2 | L | By signal only: `workflow/gtm.py`. | Other cuts. |
| Distinguish correlation from causation | WORKING | - | - | Every proposal says correlation; groups are flagged as not randomly assigned; a holdout gives a fair comparison. | - |
| Detect small samples, selection bias, attribution gaps, delays | WORKING | - | - | Sample floor, recent sends held back, results with no send counted as attribution gaps, selection flagged. | - |
| Propose changes to weights, messaging, qualification, channels | WORKING | - | - | `propose_changes`; `tests/workflow/test_gtm.py`. | - |
| Show the evidence behind each change | WORKING | - | - | Learning page. | - |
| Approval gate for material strategy changes | WORKING | - | - | Proposals need approval. | - |
| Version changes; keep prior versions; allow rollback | WORKING | - | - | Versions and rollback; `tests/workflow/test_gtm.py`. | - |
| Evaluate against a baseline or holdout | WORKING | - | - | One target in five is a holdout; `measure_experiment` compares after against the rest. Tested on fixture data. | - |
| Track whether a change improved outcomes | PARTIAL | P2 | L | Meetings per message, with verdict and advised action. | Other metrics. |
| Never learn from synthetic fixture data | WORKING | - | - | Hard filter on `mode`; a test meeting never teaches: `test_a_booked_test_meeting_never_teaches`. | - |
| Inspect, correct, approve or delete memory | WORKING | - | - | Lessons on the Learning page: approve, reject, reword, delete. | - |

### 11. Pipeline, meetings, and CRM

| Item | Status | Sev | Effort | Evidence | Missing |
|---|---|---|---|---|---|
| Define stages and entry and exit criteria | WORKING | - | - | `build_pipeline` with criteria per stage; Pipeline page. | - |
| Track account, contact, campaign, activity, meeting, opportunity, proposal, closed, renewal | MISSING | P2 | XL | Hand-entered outcomes only. No CRM is connected. | CRM connector. |
| Track booked, held, qualified, created, value, win/loss, reason | PARTIAL | P2 | L | `build_pipeline` counts each stage from outcomes; a real calendar event reached `meeting_booked`. | CRM sync. |
| Track follow-up commitments and due dates | PARTIAL | P2 | M | Commitments and next steps are insight kinds. | Due dates. |
| Deduplicate activity across integrations | MISSING | P2 | L | No CRM is connected. | - |
| Separate provider events from inferred CRM status | PARTIAL | P2 | M | Every outcome records its source. | Inferred CRM status. |
| Show next action and owner per opportunity | PARTIAL | P2 | M | Pipeline shows the next action. | Owner. |
| Reconcile attribution and flag uncertainty | MISSING | P2 | L | No CRM is connected. | - |

### 12. Finance and unit economics

| Item | Status | Sev | Effort | Evidence | Missing |
|---|---|---|---|---|---|
| Track spend by provider, channel, campaign, account, period | PARTIAL | P2 | L | Crustdata credits per run. | Other cuts. |
| Track model, data, enrichment, email, media, events, tool costs | PARTIAL | P2 | L | GLM tokens, Claude Code cost per run (actual), and manual cost entry. | A full ledger. |
| Record currency, source, date, actual or estimated, recurring | PARTIAL | P2 | M | Credits: actual vs unconfirmed estimate. | Ledger fields. |
| Show budget, actual, forecast, variance | PARTIAL | P2 | M | Per-run budget and actual. | Forecast and view. |
| Cost per account, contact, message, reply, meeting, opportunity, customer | PARTIAL | P2 | L | `finance_metrics`; Finance page. | Needs real outcomes. |
| Track pipeline, revenue, margin, CAC, payback, ROI | MISSING | P3 | L | Nothing. | Needs CRM. |
| Define attribution windows and formulas | MISSING | P3 | M | Nothing. | Formula tests. |
| Never show pipeline as revenue or estimate as actual | WORKING | - | - | `finance_metrics` keeps them apart; `tests/workflow/test_gtm.py`. | - |
| Trace metrics to records and logic | MISSING | P2 | M | Nothing. | Drill-through. |

### 13. GTM Office interface and observability

| Item | Status | Sev | Effort | Evidence | Missing |
|---|---|---|---|---|---|
| Show mission, strategy, ICP versions, accounts, stakeholders, signals, campaigns, meetings, pipeline, experiments, finance | PARTIAL | P1 | XL | 15 workspace pages in `office/src`. See `docs/GTMO_OFFICE_UI_PLAN.md`. | Several pages have little data until live accounts exist. |
| Agent click shows task, state, inputs, tools, outputs, evidence, errors, retries | PARTIAL | P1 | M | Agent dashboards and Activity tab, from hook and task records. | Inputs. |
| Full task timeline and event feed | WORKING | - | - | Mission timeline from `wf_events`; `tests/office/`. | - |
| Show Claude Code vs backend worker vs waiting on user | PARTIAL | P2 | M | Activity shows Claude Code work; Needs you shows waits. | No background worker exists. |
| Integration health and last sync per provider | PARTIAL | P1 | M | Integrations page from `claude mcp list`; `get_integration_health`. | Last sync for most connectors. |
| Idle, Running, Waiting for input/approval, Succeeded, Failed, Connection lost | WORKING | - | - | `office/src/logic.ts`, tests; Connection lost confirmed in a real browser. | - |
| Never fake progress or simulated tool activity in live mode | WORKING | - | - | The UI has no random events; `agent_status` tests. | - |
| Clearly label fixture/demo mode | WORKING | - | - | Fixture and part-fixture labels; `modeLabel` tests. | - |
| Persist state across refresh or restart | WORKING | - | - | State lives in SQLite; a real server restart resumed the same chat session. | - |
| Show source evidence next to recommendations | PARTIAL | P1 | M | Case file evidence list with status, publisher, dates. | Per-claim links. |
| Strategy and ICP version history timeline | PARTIAL | P1 | M | Version lists on the ICP and Strategy pages. | A timeline. |
| Useful empty, loading, error, retry, disconnected, denied states | PARTIAL | P1 | M | Error, retry, empty and lost states. | Not every state is tested per connector. |
| Make important changes auditable | PARTIAL | P1 | M | `wf_events` ledger; approvals record hash and actor. | Actor is a fixed string, not proven identity. |

## 5. MCP, hooks, subagents, skills, prompts and connectors
**MCP.** `trigger_point` connected in every real run. Tool errors are typed. MCP tool timeouts: not tested with a slow live call (UNVERIFIED).

**Tool gaps against the spec:** `research_market`, `compare_icp_versions`, `resolve_company_identity`, `verify_person`.

**Hooks.** `scripts/office_hook.py` handles telemetry and holds `PermissionRequest` for gated tools until a person answers in the Office. Its `PreToolUse` guard denies Gmail and Calendar writes outside the allowlist, and fails closed on any error. `PostToolUse` keeps the raw Gmail and Wispr response, so replies and transcripts never depend on a model retyping them.

**Subagents.** 8 definitions with narrow tool lists. `mission-director` and `icp-strategist` have run for real. The other six are UNVERIFIED, because they sit after discovery.

**Skills.** `review-gtm-case` (product), `build-vertical-slice` and `inspect-reference-repo` (development).

**Harness durability.**
| Check | Result |
|---|---|
| Runs through a supported harness | Yes, `claude --agent` with MCP |
| Long run | UNVERIFIED |
| Context compaction | UNVERIFIED. State is in SQLite, so it should survive |
| Tool error | WORKING: typed failure, `NEEDS_RETRY` |
| Process restart | WORKING: chat resumes the same session |
| User cancel | WORKING: Cancel in the Office |
| Approval gated in code | WORKING: recorded approval, hash binding, ask-gated tools |
| Costs and run ids | WORKING: credits, GLM tokens and Claude Code cost per run |
| Prompt and tool versions | WORKING: every engine and prompt is versioned |

**Prompts.** Five prompts, each versioned, each with a schema check. `evals/run_evals.py` holds 23 deterministic cases in 7 suites. Model quality still needs labelled live output. Agent reply JSON is not validated.

**Connectors.**
| Connector | State | Read/write | Env names | Notes |
|---|---|---|---|---|
| Crustdata REST | **Working** | Read | `CRUSTDATA_API_KEY`, `CRUSTDATA_MODE` | Identify, company, job and person search proven live. 12 of 35 endpoints enabled for this key |
| Crustdata plugin MCP | Connected to Claude Code | Read | none | Not used by Trigger Point: using it would bypass the adapter |
| Web fetch | **Working** | Read | `WEB_MODE` | SSRF guarded. No JavaScript rendering. robots.txt not consulted |
| Hyde GLM | **Working** | Read | `HYDE_INFERENCE_API_KEY`, `LLM_MODE` | Fixture mode available |
| Gmail | **Working, test inbox only** | Send, read threads | `TRIGGER_POINT_TEST_RECIPIENTS` | Hook guard denies every other recipient. Thread capture proven live; a real reply has not arrived yet |
| Google Calendar | **Working, test inbox only** | Create event, suggest time | `TRIGGER_POINT_TEST_RECIPIENTS` | Google Meet link created and recorded |
| Wispr Flow MCP | **Working** | Read only | none | Search, meeting and transcript reads. Long transcripts arrive in parts |
| HubSpot, Zoom | Failed to connect | - | - | Plugin auth incompatible |
| Salesforce, Apollo, Gong, Slack and others | Need auth | - | - | Not wired |
| Finance sources | Missing | - | - | Costs entered by hand |

## 6. Verified with real runs
| Test | Result |
|---|---|
| Office form starts a real Director, with no terminal | Pass |
| Clarifying questions reach chat | Pass |
| Server restart, then chat resumes the same session | Pass |
| Gated call held as a card in the Office | Pass |
| Deny: tool does not run | Pass |
| Approve: tool runs. Profile and ICP approved by real clicks, and the mission reached discovery | Pass |
| Live site read, 18 sourced facts, 0 unsupported | Pass |
| Live strategy step, valid against the schema | Pass |
| Live outreach for a school and a parent audience | Pass |
| Gmail send of 3 verified messages, headers read back, no bounce | Pass |
| Guard denies a recipient outside the allowlist, under real Claude Code | Pass |
| Calendar event with Google Meet, read back, invite received | Pass |
| Sends and meeting recorded and shown in the Office, labelled test | Pass |
| Real Gmail thread captured by the hook and parsed in code | Pass |
| Real Wispr transcript captured, parsed and quote-checked, on a copy of the database | Pass |
| Whole loop clicked through in a real browser on fixture data: reply, review, proposal, approval, version, measurement, keep | Pass |
| Live Crustdata company search, job search and person search against real accounts | Pass |
| Live funding signal: a real `/company/search` call, through `signals_from_company`, produces a correctly dated `recent_funding` signal for `crustdata.com`'s real seed round | Pass |
| A full live mission (profile, strategy, ICP, discovery, signals, people, score) on `learntulip.com`, run twice, correctly rejecting every account with `no_fresh_why_now` because the 11 real Mumbai schools found have no job postings or funding on Crustdata | Pass |
| The Office's Integrations page shows Crustdata as live, with a real timestamp, after a real discovery run | Pass |

| Live discovery on a real seller: real Mumbai schools found | Pass |
| Live person search: employer id present, so the current-employer check works | Pass |
| Full live mission through scoring, stopped honestly with no qualified account | Pass |

**Why-now result.** Crustdata's job index returned 0 postings at any date for all 11 schools found. A news search for one school returned nothing, and web and news results carry no date field. Hiring cannot supply a why-now for this market.

**Deliverability result.** The invite reached the test inbox with an "unknown sender" label. The test emails landed in spam there, as reported by the recipient.

## 7. Still UNVERIFIED
- The Director running **Check replies**, **Import from Wispr Flow** and **Review what we learned**. The parts are proven; the whole run needs a person's click on each held read.
- A real reply reaching the Replies card.
- The **Send to test inbox**, **Book test meeting** and scheduled-send paths, which need a click on the held card.
- A held prompt inside a subagent.
- Everything after discovery under real Claude Code, including six subagents.
- Case file, draft and gate on a live account, which need a qualified account first.

## 8. GTM workflow gaps
In order of user impact: no live accounts; purely client-rendered sites; no outside market research; one case file per mission. Details in section 4.

**Reaching parents.** Crustdata finds schools as organisations, but not parents, so parents need a different channel.

## 9. ICP and stakeholder gaps
- ICP criteria have no evidence link per criterion, and no segment list.
- Eight of the ten spec dimensions are absent.
- Stakeholder roles are inferred from titles, and messages are per audience, not per named person.

## 10. Wispr Flow and meeting gaps
Wispr is read only. Meetings match accounts by calendar id or a target's name, so a meeting with neither goes to a person. Attendee emails are not returned by `get_meeting`, and nothing updates a CRM.

## 11. Self-improvement gaps
| Step | State |
|---|---|
| 1. Capture a verified event or correction | Yes: raw Gmail and Wispr, plus reviewed corrections |
| 2. Link it | Yes: message, audience, strategy and ICP version |
| 3. Extract a candidate lesson | Yes: the Director proposes, with evidence ids |
| 4. Check it | Yes: sample, recency, attribution, one-source refusal. Contradictions between insights are not checked |
| 5. Propose a change | Yes |
| 6. Approve | Yes: only in the Office |
| 7. Version it | Yes: guidance in a new strategy version |
| 8. Measure | Yes: against a holdout and earlier work. Sequential changes can overlap |
| 9. Keep or roll back | Yes: rollback retires the lesson |

**Limits.** An approved change reaches prompts as guidance. It does not change score-v1 weights, which stay deterministic and versioned in code. Real sends are logged by a person, because outreach to real recipients stays blocked.

## 12. Finance gaps
Cost per unit, pipeline and revenue figures work from hand-entered records. There is no CRM, attribution window or forecast. Estimates are never shown as actuals.

## 13. Security and approval gaps
| Finding | Sev | Note |
|---|---|---|
| Actor in approvals is a fixed string | P1 | It proves no identity |
| Gate depends on Claude Code permissions | P1 | `bypassPermissions` removes it |
| DNS-rebinding window in fetcher | P2 | Fix before hosting |
| robots.txt not consulted | P2 | Fix before wider crawling |
| Traction check is a keyword rule | P2 | A person must read each message |
| No tenant isolation | P3 | Local only |

**Working:** token, Host and Origin guards on the API; loopback only; no Trigger Point send tool; recipient allowlist; hash-bound approvals; recheck against current rules before a message is prepared or approved; redaction; `0600` token file.

## 14. Roadmap
See `docs/GTMO_IMPLEMENTATION_ROADMAP.md`.

## 15. What each remaining gap needs
| Gap | Needs |
|---|---|
| A why-now for schools | A decision on a signal source. See `docs/CRUSTDATA_INTEGRATION.md` |
| Outside market research | A web search connector |
| Wispr Flow meetings | Notetaker and MCP access |
| CRM sync | A HubSpot or Salesforce connection |
| Inbox placement for real outreach | A company domain with SPF, DKIM and DMARC |
| Unattended reads | Allow the Gmail and Wispr reads in `.claude/settings.json`, or click each held card |
| Reaching parents | A channel other than Crustdata |
| Sending to real recipients | A decision, then a tested path |
| Client-rendered sites | Build work: a rendering step |

## Definition of done (spec Part F)
| Check | Status |
|---|---|
| Audit separates verified from assumed | Yes |
| Real website and goal create a persistent mission | Yes |
| Review and approve profile and strategy | Yes |
| ICP has evidence, criteria, exclusions, versions | Partial: no evidence per criterion |
| Discovery and people use real providers | Unverified |
| Signals have verified sources and event dates | Fixtures only |
| Explainable score and case file per account | Yes, on fixtures |
| Role-specific purpose and message per stakeholder | Partial: per audience |
| Draft, scheduled, sent are different states | Yes |
| No external send without approval | Yes |
| Wispr insights traceable | Yes |
| Strategy change proposal with evidence | Yes |
| Approved change creates a version | Yes |
| Finance formulas tested | Yes |
| Office displays real activity | Yes |
| Refresh and reconnect preserve state | Yes |
| Live and fixture distinct | Yes |
| Errors, retries, health, permission waits visible | Yes |
| Relevant tests pass | Yes |
| Docs explain setup, env, limits, demo | Yes |
