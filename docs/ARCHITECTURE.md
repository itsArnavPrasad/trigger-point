# Architecture

## Architecture rule
Use a small explicit pipeline. Add agent frameworks only when stateful branching, resumability or parallel research demonstrably needs them. A collection of agents is not automatically better than one orchestrator with typed stages.

## Components
```text
Browser -> FastAPI /api/office -> Mission Runner -> claude --agent mission-director
                 |                                      | MCP            | hooks
                 v                                      v                v
              SQLite  <------------- Trigger Point core        scripts/office_hook.py
```

| Component | Responsibility | State |
|---|---|---|
| Claude Code harness | Runs the agent workflow, invokes tools, coordinates subagents | Built |
| Trigger Point core | Domain logic, mission state, scores, evidence, rules, approvals, outcomes | Built |
| MCP server | Narrow, typed tools. Only workflow tools can change a mission. None can approve learning | Built, 36 tools |
| Hooks | Lifecycle telemetry and deterministic controls | Built |
| Mission Runner | Starts and resumes the Director from the Office (`office/runner.py`) | Built |
| Scheduler | Asks the Director when a scheduled send is due (`office/scheduler.py`). The send is still held for a click | Built |
| Feedback loop | `workflow/loop.py` (pure rules), `workflow/feedback.py`: raw capture, replies, meetings, lessons, experiments | Built |
| Database and event log | State, events, artifacts, evidence, approvals, versions | Built |
| Office backend | `src/trigger_point/office`: token auth, dashboards, held approvals, live ticks | Built |
| Office UI | `office/`. Renders authoritative state, never invents progress | Built |
| Connectors | Crustdata, Wispr Flow, CRM, email, calendar, web research, finance. Each declares capabilities and limits | Web, Gmail, Calendar and Wispr live; Crustdata untested; rest missing |

**Raw capture.** The `PostToolUse` hook stores Gmail and Wispr responses as returned. Code parses them, so a reply or transcript never depends on a model retyping it.

**Use each mechanism for its job.** `CLAUDE.md` for concise context. Skills for repeatable procedures. Subagents for bounded work with structured results. MCP for typed access. Hooks for telemetry and controls. Application code for durable state, retries, scoring, validation and approvals. Hooks are never the workflow engine, and a prompt alone never enforces safety.

## Mission states
`RECEIVED → PROFILE_REVIEW → ICP_READY → ACCOUNTS_FOUND → SIGNALS_RESEARCHED → PEOPLE_MAPPED → EVIDENCE_VERIFIED → CAMPAIGN_DRAFTED → USER_APPROVAL → COMPLETE`, plus `WAITING_FOR_INPUT`, `NEEDS_RETRY`, `FAILED`, `CANCELLED`.

Every transition is persisted. `src/trigger_point/workflow/` owns order, tasks, approvals and events. The stage records below own their content.

| Stage | Record | Status values |
|---|---|---|
| Intake and review | `RunReceipt`, `BusinessContext` vN | `review_required`, `approved` (append-only versions) |
| ICP plan | `Mission`, `IcpVersion` | `review_required`, `approved` |
| Discovery | `DiscoveryRun` | `completed`, `completed_empty`, `failed` |
| Signals, people, scores | `ResearchRun` | `completed`, `failed`, with per-stage notes |
| Case file | `AccountCase` | route: `cold_email`, `research_more`, `do_not_contact` |
| Drafts and outreach | `CampaignDraft`, outreach records | `verified`, `rejected`, `approved` |

Replay is `mode="replay"` on every record, not a separate state.

## Agents
Mission Director, ICP Strategist, Account Scout, Signal Analyst, Buying Committee Mapper, Evidence Auditor, Campaign Architect and Quality Gatekeeper, in `.claude/agents/`.

## Model use
Claude Code runs the workflow. GLM via Hyde performs bounded structured steps behind `StructuredLlm`. Deterministic code owns scores, validation, identity and approvals. SQLite is the system of record.

**Why.** GLM 5.3 Flash steps take 7 to 180 s, so an agent loop on the critical path would be slow and non-deterministic. Typed tools keep every invariant (SSRF guard, grounding, budgets, approval) in code.

**Consequences.**
- Agents can never call providers, URLs or SQL directly.
- Approval and credit-spending tools are gated by Claude Code's `permissions.ask`.
- Provider modes are per provider (`WEB_MODE`, `LLM_MODE`, `CRUSTDATA_MODE`). A run is labelled `live`, `replay` or `mixed` by the providers it actually used.

## Provider adapter contract
Use a normalized internal interface rather than leaking provider payloads through the app. Each adapter method should:
- validate inputs and outputs
- return normalized data plus provenance and metadata
- expose usage and cost headers when available
- map provider errors into typed application errors
- respect timeouts and rate limits, and retry only safe operations
- support fixture replay
- redact secrets and unnecessary personal data

## Event schema
`event_id`, `mission_id`, `task_id`, `agent_id`, `event_type`, `occurred_at`, `recorded_at`, `status`, `correlation_id`, `summary`, `artifact_ids`, `schema_version`, ordered per mission by `seq`.

## Persistence
SQLite. Move to PostgreSQL when deployed. Unstructured conversation history is never the only source of truth.
