# Data Model

Use Pydantic models for API contracts and explicit database tables for persistence. Fields below are conceptual; refine them with migrations and tests.

## BusinessContext
- `id`, `tenant_id`
- `website_url`, `company_name`, `domain`
- `product_summary`
- `value_propositions[]`
- `use_cases[]`
- `target_segments[]`
- `buyer_personas[]`
- `approved_proof_points[]`
- `competitors[]`
- `exclusions[]`
- `unknowns[]`
- `source_refs[]`
- `status`: `draft | review_required | approved | archived`
- `version`, `created_at`, `updated_at`

## GTMPlan
- `id`, `business_context_id`, `user_goal`
- `icp_filters`, `geography`, `company_stage`, `company_size`
- `personas[]`, `signal_types[]`, `exclusions[]`
- `max_accounts`, `freshness_policy`, `budget_limit`
- `channel_preferences[]`, `campaign_goal`
- `assumptions[]`, `relaxation_policy`
- `status`, `created_at`

## Account
- `id`, `provider`, `provider_company_id`, `canonical_domain`
- `name`, `description`, `industry`, `employee_range`, `funding_stage`
- `source_refs[]`, `raw_payload_hash`, `last_verified_at`
- unique identity constraints on provider ID and normalized domain where appropriate

## Person
- `id`, `provider`, `provider_person_id`
- `full_name`, `current_title`, `current_company_id`
- `role_status`, `tenure`, `source_refs[]`, `last_verified_at`
- Avoid collecting personal fields that are not necessary for the stated business purpose.

## Evidence
- `id`, `entity_type`, `entity_id`, `claim_text`
- `source_url`, `source_title`, `publisher`
- `published_at` (nullable), `retrieved_at`
- `supporting_excerpt`, `content_hash`
- `verification_status`: `supported | partial | unsupported | stale | entity_mismatch | inaccessible`
- `source_kind`, `confidence`, `notes`

## Signal
- `id`, `account_id`, optional `person_id`
- `type`, `description`, `event_at` (nullable), `observed_at`
- `source_evidence_id`, `strength`, `freshness_days`
- `status`: `active | decayed | expired | invalidated`
- unique dedupe key derived from canonical entity + type + source + event/content identity

## AccountCase
- `id`, `mission_id`, `account_id`, `state`
- `why_account[]`, `why_person[]`, `why_now[]`, `why_us[]`
- `score_total`, `score_breakdown`, `score_version`
- `recommended_route`, `next_best_action`
- `coverage_gaps[]`, `verifier_results[]`
- `created_at`, `updated_at`, `expires_at`

## CampaignDraft
- `id`, `case_id`, `channel`, `recipient_id`
- `subject`, `body`, `follow_up_steps[]`
- `claim_evidence_map[]`, `content_hash`
- `status`: `draft | needs_revision | approved | rejected | sent`
- `approved_by`, `approved_at`

## RunReceipt
- `id`, `mission_id`, `mode`: `live | replay`
- `provider_calls[]`, `credits_used`, `estimated_cost`, `actual_cost`
- `started_at`, `finished_at`, `stage_durations`, `cache_hits`, `errors[]`
- `data_coverage`, `score_version`, `app_version`

## Approval / ActionLog
Record exact action, recipient, channel, content hash, approver, timestamp, policy checks, result, provider request ID. No approval record means no external send.

## As implemented
These are the Pydantic models, in `src/trigger_point/`. They differ from the conceptual fields above as follows.

- **BusinessContext** (`models/context.py`)
  - Every list item is a `ContextClaim(text, kind: fact|inference|user_provided, source_url, excerpt, confidence, status, status_reason, verification_method)`. These are claims, not plain strings.
  - Versions are append-only.
  - Also carries `mode`, `provider_modes`, `run_id`, `approved_at` and `approved_by`.
- **GTMPlan** (`mission/models.py`)
  - Countries are Crustdata values.
  - `employee_ranges` are provider buckets.
  - Personas carry a role function.
  - Also carries `tech_keywords`, `freshness_days` and `credit_budget`.
  - The compiled Crustdata request is stored next to the plan on `Mission.search_request`.
- **Account → `Company`** (`providers/crustdata/models.py`). Normalised. Missing data stays `None`. Identity is the `provider_company_id` plus the primary domain, deduplicated in `mission/selection.py`.
- **Person → `PersonRecord`.** Name, current title, current employer ids, role start, profile URL, provider `updated_at`, and `contact`: an optional list of email and phone points (value, business or personal, the provider's deliverability status). `contact` is empty unless contact details were bought from Crustdata (person enrich); our search never requests them. They are shown to the user only and never copied into evidence, drafts, prompts or event text.
- **Evidence** (`models/evidence.py`)
  - `published_at` is split into `event_on` (when it happened, e.g. a job posted date) and `as_of` (when the provider measured or refreshed it). Both are separate from `retrieved_at`.
  - The id is content-based and stable across runs.
  - Verification status lives on the claim that cites the evidence (context grounding, draft verifier), not on the evidence itself.
- **Signal** (`research/signals.py`). `type`, `event_on`, `as_of`, `age_days`, `window_days`, `status: active|expired|undated`, `strength`, `evidence_ids`, plus a version.
- **AccountCase** (`cases/models.py`)
  - The four whys are lists of `CaseItem(text, kind: fact|inference|unknown, evidence_ids)`.
  - Also: `score` (`ScoreBreakdown`, versioned), route, next action, coverage gaps, warm path, recipient, hook and seller evidence ids, `expires_on`, and the evidence list.
- **CampaignDraft** (`drafts/models.py`)
  - Claim-to-evidence map, hook and proof-point ids, a follow-up plan, a `content_hash` over (recipient, channel, subject, body), `status: verified|rejected|approved`, the verifier log, and `sending: "disabled"`.
- **RunReceipt / CallRecord / DiscoveryRun / ResearchRun.** Mode, initiator, every provider call (actual vs estimated credits, attempts, cache, replay source), notes and errors.
- **Approval / ActionLog.** For drafts: `approved_by`, `approved_at` and `approved_hash`. Test sends store the provider message and thread ids on the outreach record.

## Mission workflow
In `src/trigger_point/workflow/`, tables `wf_missions`, `wf_tasks`, `wf_approvals`, `wf_evidence`, `wf_events`.
- **WorkflowMission:** state, resume state, mode, and links to the stage records.
- **WorkflowTask:** one per mission and kind, with status, attempt, output, error.
- **WorkflowApproval:** gate, target hash, decision, actor.
- **WorkflowEvent:** ordered per mission by `seq`; the Office reads it directly.
- **EvidenceRecord:** evidence with audit-v1 status and reasons.

`IcpVersion` (`wf_icp_versions`): criteria with kind, basis and confidence, gaps, author, rationale, changes. Office tables: `office_activity`, `office_permissions`, `office_messages`, `office_runs`, `office_costs`, `office_changes`.

`gtm_records`: strategy versions, outcomes, meetings, manual costs, proposals. Pure logic in `workflow/gtm.py`.

`gtm_records` also holds the feedback loop:
- **raw_source:** a Gmail or Wispr response as returned. Never sent to the page.
- **reply:** sender, text, kind (`reply`, `opted_out`, `bounced`), and a person's label.
- **suppression:** a target that must not be contacted.
- **touch:** a real send a person logged, or a labelled demo send. Test sends are read from the outreach record.
- **insight:** kind, text, basis, quote, speaker, status, and the original text if corrected.
- **lesson:** text, target, evidence ids, wording history, status, mode, seller domain, strategy version.
- **experiment:** change, version, metric, decision rule, status.

Outcomes carry `outreach_id`, `audience` and `strategy_version`. Outreach records carry `schedule`, `step`, `follow_up_of`, `variant` and `lessons_used`.

## Planned for the GTM OS (not built)
- **Claim classes:** fact, user statement, assumption, hypothesis, recommendation.
- **Evidence additions:** `source_title`, `published_at`, `relevance`. Status `VERIFIED | NEEDS_REVIEW | CONTRADICTED | STALE`.
- **MarketMap, CompetitorRecord:** observed facts apart from inferred strategy.
- **StrategyVersion; IcpVersion additions:** segments, weights, evidence per criterion.
- **CommitteeRole, PersonaProfile, Stakeholder:** known person vs inferred role.
- **GtmPlan, Channel, Sequence, Experiment.**
- **Opportunity, PipelineStage, Activity.**
- **CostEntry:** amount, currency, source, date, actual or estimated, recurring.
- **IntegrationHealth history:** today's view is computed, with no sync record.

