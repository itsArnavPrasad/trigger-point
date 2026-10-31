/** The UI's rules, kept pure so they can be tested. Nothing here invents state. */

import type { Agent, Mission, MissionView, Permission } from './types'

export const FLOW = ['RECEIVED', 'PROFILE_REVIEW', 'ICP_READY', 'ACCOUNTS_FOUND', 'SIGNALS_RESEARCHED', 'PEOPLE_MAPPED', 'EVIDENCE_VERIFIED', 'CAMPAIGN_DRAFTED', 'USER_APPROVAL', 'COMPLETE']
const TERMINAL = ['COMPLETE', 'FAILED', 'CANCELLED']

const STATE_LABEL: Record<string, string> = {
  RECEIVED: 'Received', PROFILE_REVIEW: 'Profile review', ICP_READY: 'ICP ready', ACCOUNTS_FOUND: 'Accounts found',
  SIGNALS_RESEARCHED: 'Signals researched', PEOPLE_MAPPED: 'People mapped', EVIDENCE_VERIFIED: 'Evidence verified',
  CAMPAIGN_DRAFTED: 'Campaign drafted', USER_APPROVAL: 'Your approval', COMPLETE: 'Complete',
  WAITING_FOR_INPUT: 'Waiting for input', FAILED: 'Failed', CANCELLED: 'Cancelled', NEEDS_RETRY: 'Needs retry',
}
const STATUS_LABEL: Record<string, string> = {
  idle: 'Idle', queued: 'Queued', running: 'Running', waiting_approval: 'Waiting for approval',
  waiting_input: 'Waiting for input', succeeded: 'Succeeded', failed: 'Failed', cancelled: 'Cancelled',
}
const TOOL_LABEL: Record<string, string> = {
  approve_business_profile: 'Approve the business profile',
  approve_icp_plan: 'Approve the ICP and its credit estimate',
  discover_accounts: 'Search for accounts (spends Crustdata credits)',
  research_account_signals: 'Research buying signals (spends Crustdata credits)',
  map_buying_committee: 'Find the buying committee (spends Crustdata credits)',
  approve_campaign_draft: 'Approve this exact draft (nothing is sent)',
}

export const STAGE_ORDER = ['reply', 'positive_reply', 'meeting_booked', 'meeting_held', 'opportunity_created', 'closed_won']

/** Totals by currency. Different currencies are never added together. */
export function money(totals: Record<string, number>): string {
  const parts = Object.entries(totals).map(([c, n]) => `${n.toLocaleString('en-US')} ${c}`)
  return parts.length ? parts.join(' + ') : '0'
}

export const stateLabel = (s: string) => STATE_LABEL[s] ?? s
export const statusLabel = (s: string) => STATUS_LABEL[s] ?? s

export function modeLabel(mode: string): string {
  if (mode === 'replay') return 'FIXTURE DATA'
  if (mode === 'mixed') return 'PART FIXTURE'
  return mode === 'live' ? 'LIVE' : 'UNKNOWN'
}

export function permissionLabel(p: Pick<Permission, 'tool'> & Partial<Pick<Permission, 'input'>>): string {
  const tool = p.tool.replace('mcp__trigger_point__', '')
  if (tool.endsWith('Gmail__send_message')) return `Send test email to ${(p.input?.to ?? []).join(', ')}: ${p.input?.subject ?? ''}`
  if (tool.endsWith('Calendar__create_event')) return `Create calendar event: ${p.input?.summary ?? ''}`
  return TOOL_LABEL[tool] ?? `Allow ${tool}`
}

export function flowSteps(m: Pick<Mission, 'state' | 'resume_state'>) {
  const at = FLOW.indexOf(FLOW.includes(m.state) ? m.state : m.resume_state ?? '')
  return FLOW.map((state, i) => ({ state, label: stateLabel(state), phase: m.state === 'COMPLETE' || i < at ? 'done' : i === at ? 'current' : 'todo' }))
}

/** Five plain-language phases over the mission's state machine, for the dashboard's journey track. */
export const JOURNEY = [
  { id: 'understand', label: 'Understand', states: ['RECEIVED', 'PROFILE_REVIEW'] },
  { id: 'target', label: 'Target', states: ['ICP_READY'] },
  { id: 'research', label: 'Research', states: ['ACCOUNTS_FOUND', 'SIGNALS_RESEARCHED', 'PEOPLE_MAPPED', 'EVIDENCE_VERIFIED'] },
  { id: 'engage', label: 'Engage', states: ['CAMPAIGN_DRAFTED', 'USER_APPROVAL'] },
  { id: 'learn', label: 'Learn', states: ['COMPLETE'] },
]

export function journey(m: Pick<Mission, 'state' | 'resume_state'>) {
  const s = FLOW.includes(m.state) ? m.state : m.resume_state ?? ''
  const at = JOURNEY.findIndex(p => p.states.includes(s))
  return JOURNEY.map((p, i) => ({ id: p.id, label: p.label, phase: at < 0 || i > at ? 'todo' : i < at ? 'done' : 'current' }))
}

/** Upcoming meetings soonest first, past meetings latest first. Dates are ISO days. */
export function splitMeetings<T extends { held_on: string }>(meetings: T[], today: string) {
  const upcoming = meetings.filter(m => m.held_on >= today).sort((a, b) => a.held_on.localeCompare(b.held_on))
  const past = meetings.filter(m => m.held_on < today).sort((a, b) => b.held_on.localeCompare(a.held_on))
  return { upcoming, past }
}

export type MeetingStatus = 'today' | 'upcoming' | 'held' | 'missed' | 'cancelled' | 'needs_update'

/** A past meeting counts as held only when someone said so or wrote notes; otherwise it needs an update. */
export function meetingStatus(m: { held_on: string; status?: string | null; notes?: string | null }, today: string): MeetingStatus {
  if (m.status === 'missed' || m.status === 'cancelled') return m.status
  if (m.held_on > today) return 'upcoming'
  if (m.held_on === today) return m.status === 'held' ? 'held' : 'today'
  return m.status === 'held' || m.notes?.trim() ? 'held' : 'needs_update'
}

/** What the office can vouch for. A stopped stream means Connection lost, never "still running". */
export function agentLabel(a: Pick<Agent, 'status'>, connected: boolean): string {
  if (!connected) return a.status === 'running' ? 'Connection lost' : statusLabel(a.status)
  return statusLabel(a.status)
}

export type Liveness = 'lost' | 'needs_you' | 'working' | 'idle' | 'ended'

/** `busy` means the Director is mid-turn. A live process that has finished its turn is waiting. */
export function liveness(v: (Pick<MissionView, 'mission' | 'permissions' | 'tasks' | 'approvals'> & { run?: MissionView['run'] }) | null, connected: boolean, busy: boolean): Liveness {
  if (!connected) return 'lost'
  if (!v) return 'idle'
  if (TERMINAL.includes(v.mission.state)) return 'ended'
  if (v.permissions.length || v.mission.state === 'WAITING_FOR_INPUT') return 'needs_you'
  if (busy || v.tasks.some(t => t.status === 'running')) return 'working'
  return v.run?.status === 'idle' ? 'needs_you' : 'idle'
}

export const LIVENESS_LABEL: Record<Liveness, string> = { lost: 'Connection lost', needs_you: 'Needs you', working: 'Working', idle: 'Idle', ended: 'Finished' }

/** Only http(s) becomes a link, whatever a source says. */
export function safeHref(url?: string | null): string | undefined {
  return url && /^https?:\/\//i.test(url) ? url : undefined
}

export function elapsed(from?: string | null, to?: string | null, now = Date.now()): string {
  const start = from ? Date.parse(from) : NaN
  if (!Number.isFinite(start)) return ''
  const s = Math.max(0, Math.round(((to ? Date.parse(to) : now) - start) / 1000))
  return s < 60 ? `${s}s` : s < 3600 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${Math.floor(s / 3600)}h ${Math.floor(s / 60) % 60}m`
}

export function tokenFromHash(hash: string): string | null {
  const m = /[#&]token=([0-9a-f]{32,128})/.exec(hash)
  return m ? m[1] : null
}

export const RESULT_TEXT: Record<string, string> = {
  insufficient: 'Not enough results yet', improved: 'Improved', worse: 'Worse', no_change: 'No clear change',
}

/** A rate means nothing without its base, so no sends shows as unknown rather than 0%. */
export function percent(rate: number, n: number): string {
  return n ? `${Math.round(rate * 100)}%` : 'Unknown'
}

const SIGNAL_LABELS: Record<string, string> = {
  topic_engagement: 'Staff post about the topic',
  recent_funding: 'Recent funding',
  active_hiring: 'Hiring now',
  support_team_growth: 'Hiring into the target team',
  headcount_growth: 'Headcount growth',
}

/** A signal type in the words a person would use. An unknown type still shows, just less polished. */
export function signalLabel(type: string): string {
  return SIGNAL_LABELS[type] ?? type.replaceAll('_', ' ')
}
