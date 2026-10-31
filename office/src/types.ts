/* eslint-disable @typescript-eslint/no-explicit-any */
export interface Mission { id: string; website_url: string; goal: string; state: string; resume_state?: string | null; wait_reason?: string | null; failure?: string | null; mode: string; provider_modes: Record<string, string>; created_at: string }
export interface MissionRow { id: string; state: string; mode: string; website_url: string; goal: string }
export interface Task { id: string; kind: string; role: string; title: string; status: string; attempt: number; started_at: string | null; finished_at: string | null; output: Record<string, any>; error: { kind: string; message: string; retryable: boolean } | null }
export interface MissionEvent { event_id: string; seq: number; event_type: string; occurred_at: string; role: string | null; status: string; summary: string; data: Record<string, any> }
export interface Agent { role: string; name: string; purpose: string; status: string; task: Task | null; tasks: Task[]; step: string | null; tools: MissionEvent[]; hook_activity: { summary: string; at: string; kind: string }[] }
export interface Permission { id: string; tool: string; input: Record<string, any>; dashboard: string; role: string | null; at: string }
export interface Approval { id: string; gate: string; summary: string; status: string; target_hash: string; dashboard: string; decided_by: string | null; reason: string | null }
export interface Claim { text: string; kind: string; status: string; source_url: string | null; excerpt: string | null; confidence: string; status_reason?: string | null }
export interface Profile { context_id: string; version: number; status: string; company: string | null; domain: string; goal: string; readability: string; target_geography: string | null; time_horizon: string | null; claims: Record<string, Claim[]>; unknowns: string[]; questions: string[]; pages: { url: string; fetch_status: string; title: string | null; error: string | null }[]; versions: { version: number; status: string; at: string }[] }
export interface Criterion { dimension: string; statement: string; kind: string; basis: string; confidence: string }
export interface Icp { version: number; status: string; created_at: string; author: string; rationale: string; changes: string[]; icp_query: string; criteria: Criterion[]; personas: { title: string; function: string | null; why: string }[]; gaps: string[]; assumptions: string[]; open_questions: string[]; estimated_credits: string; method: string }
export interface Signal { id: string; type: string; description: string; event_on: string | null; as_of: string | null; age_days: number | null; window_days: number; status: string; strength: number }
export interface Stakeholder { sequence: number; purpose: string; ask: string; known: boolean; name?: string | null; title: string | null; role: string; confidence?: number; employer_verified?: boolean; reason?: string; why?: string; profile_url?: string | null }
export interface Score { total: number; coverage: number; status: string; tier: string | null; version: string; rejections: string[]; components: Record<string, { value: number | null; known: boolean; detail: string }> }
export interface Account { id: number; name: string | null; domain: string | null; country: string | null; size: string | null; industries: string[]; growth_6m: number | null; openings: number | null; score: Score; signals: Signal[]; stakeholders: Stakeholder[]; people_searched: boolean; people_rejected: { current_title: string | null; reason: string }[] }
export interface Funnel { found: number; removed: number; kept: number; qualified: number; insufficient: number; rejected: number; awaiting: number; removed_accounts: { name: string | null; reason: string }[]; relaxations: string[]; calls: { endpoint: string; ok: boolean; result_count: number | null; mode: string; credits_used: string | null }[]; credits: Record<string, string> }
export interface Evidence { id: string; account: string | null; entity_type: string; claim: string; source_url: string | null; provider_ref: string | null; publisher: string | null; event_on: string | null; as_of: string | null; retrieved_at: string; excerpt: string | null; verification_status: string; verification_reasons: string[]; signal_status: string }
export interface Draft { id: string; account_name: string | null; recipient_name: string | null; recipient_title: string | null; channel: string; subject: string; body: string; status: string; sending: string; content_hash: string; claims: { text: string; kind: string; evidence_ids: string[] }[]; follow_ups: { day_offset: number; angle: string }[]; verifier_log: { attempt: number; outcome: string; source: string; findings: { code: string; severity: string; message: string }[] }[] }
export interface Health { id: string; name: string; purpose: string; state: string; access: string; last_success: string | null; note?: string }
export interface Harness { id: string; name: string; purpose: string; state: string; wired: boolean }
export interface Message { seq: number; sender: string; text: string; at: string }
export interface MissionView {
  mission: Mission; tasks: Task[]; agents: Agent[]; permissions: Permission[]; approvals: Approval[]
  profile: Profile | null; icp: Icp[]; funnel: Partial<Funnel>; accounts: Account[]; notes: string[]; evidence: Evidence[]
  case: Record<string, any> | null; draft: Draft | null; gate: { passed: boolean; version: string } | null; gate_error: string | null
  costs: { entries: { source: string; amount: number; unit: string; basis: string; at: string }[]; claude_usd: number; crustdata_credits: Record<string, string> }
  strategy: { version: number; status: string; author: string; changes: string[]; mode: string; rolled_back_to: number | null; body: Record<string, any> }[]
  targets: { id: string; name: string; audience: string; notes: string; source: string; account_id?: number; signal_types?: string[]; why_now?: string[] }[]
  outreach: Outreach[]
  meetings: { id: string; title: string; held_on: string; time?: string; account_name?: string | null; attendee?: string; attendee_role?: string; audience?: string; status?: string; notes?: string; prep?: string; summary?: string; learnings?: string[]; source: string; link?: string | null; needs_review?: boolean; match_basis?: string; progress?: string | null; strategy_version?: number | null; icp_version?: number | null }[]
  pipeline: { accounts: { account_id: number | null; account_name: string | null; stage: string; last_activity: string; next_action: string | null; value: number | null; currency: string | null; mode: string }[]; counts: Record<string, number>; criteria: Record<string, string>; open_pipeline: Record<string, number>; won_revenue: Record<string, number> }
  outcomes: { id: string; kind: string; account_name: string | null; occurred_on: string; mode: string; note: string | null }[]
  learning: Learning
  finance: { metrics: Record<string, number | null>; manual: { id: string; label: string; amount: number; currency: string; basis: string; recurring?: boolean; on?: string }[]; excluded_other_currency: number }
  messages: Message[]; run: { status: string; detail: string | null } | null; events: MissionEvent[]; running: boolean
}
export interface Outreach { id: string; target_id: string; target_name: string; audience: string; purpose: string; ask: string; subject: string; body: string; status: string; sending: string; content_hash: string; mode: string; step?: number; variant?: string; lessons_used?: string[]; test_sends?: { to: string; message_id: string }[]; manual_sends?: { sent_on: string }[]; schedule?: { send_at: string; timezone: string; state: string; channel: string; recipient: string; step: number; error: string | null } | null; attempts: { attempt: number | string; findings: { code: string; message: string }[] }[] }
export interface Lesson { id: string; text: string; target: string; sources: number; single_source: boolean; status: string; history: string[]; strategy_version: number | null }
export interface Experiment { id: string; change: string; version: number; metric: string; rule: string; status: string; result: { verdict: string; action: string; after_rate: number; after_n: number; before_rate: number; before_n: number } }
export interface Learning {
  demo: boolean; steps: { name: string; count: number }[]
  replies: { id: string; target_name: string; sender: string; body: string; received_on: string; kind: string; label: string | null }[]
  suppressions: { id: string; target_name: string; reason: string }[]
  lifecycle: Record<string, { state: string; reached: string[] }>
  insights: { id: string; kind: string; text: string; basis: string; quote: string; speaker: string | null; status: string; account_name: string | null; original_text: string | null; source_link: string | null }[]
  lessons: Lesson[]; experiments: Experiment[]
  decisions: { id: string; change: string; evidence: string; status: string; dimension?: string | null; value?: string | null }[]
  timeline: { version: number; author: string; changes: string[]; rolled_back_to: number | null; guidance: string[] }[]
  report: {
    counted: number; excluded: number; pending: number; attribution_gaps: number; maturity_days: number; min_sample: number
    groups: { dimension: string; value: string; n: number; wins: number; rate: number; enough: boolean }[]
    proposals: { dimension: string; value: string; target: string; sample: number; rate: number; baseline: number; change: string; caveat: string; checks: { alternatives: string }; outcome_ids: string[] }[]
  }
}
export interface Bootstrap { missions: MissionRow[]; health: Health[]; harness: Harness[]; mode: string; provider_modes: Record<string, string> }
