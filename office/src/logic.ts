/** The UI's rules, kept pure so they can be tested. Nothing here invents state. */

import type { Account, Agent, Harness, Mission, MissionView, Permission, Score } from './types'

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
  map_buying_committee: 'Find the buying committee and look up their email and phone (spends Crustdata credits)',
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


export const SCORE_PARTS = ['fit', 'timing', 'reachability', 'evidence_quality'] as const
export const SCORE_LABEL: Record<string, string> = { fit: 'Fit', timing: 'Timing', reachability: 'Reach', evidence_quality: 'Evidence' }
export const SCORE_HELP: Record<string, string> = {
  fit: 'How closely it matches your ideal customer',
  timing: 'Fresh reasons to talk to them now',
  reachability: 'A verified person you can contact',
  evidence_quality: 'How well sourced the facts are',
}
const GOOD: Record<string, string> = { fit: 'a good fit', timing: 'fresh signals', reachability: 'a verified contact', evidence_quality: 'solid evidence' }
const WEAK: Record<string, string> = { fit: 'a weak fit', timing: 'no fresh signal', reachability: 'no verified contact', evidence_quality: 'thin evidence' }
const UNKNOWN: Record<string, string> = { fit: 'fit unknown', timing: 'timing unknown', reachability: 'contact unknown', evidence_quality: 'evidence unknown' }
export const REJECTION: Record<string, string> = {
  no_relevant_buyer: 'no relevant decision-maker found there',
  no_fresh_why_now: 'no fresh reason to talk now',
  identity_unresolved: 'could not confirm which company this is',
}
const list = (xs: string[]) => (xs.length > 1 ? `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}` : xs[0])
const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1)

/** One plain sentence on why an account ranks where it does. Built from the stored components, never from a model. */
export function scoreLine(s: Pick<Score, 'status' | 'rejections' | 'components'>): string {
  if (s.rejections.length) return `Rejected: ${list(s.rejections.map(r => REJECTION[r] ?? r.replaceAll('_', ' ')))}.`
  const strong: string[] = [], weak: string[] = [], unknown: string[] = []
  for (const k of SCORE_PARTS) {
    const c = s.components[k]
    if (!c || !c.known || c.value === null) unknown.push(UNKNOWN[k])
    else if (c.value >= 70) strong.push(GOOD[k])
    else if (c.value < 50) weak.push(WEAK[k])
  }
  const gaps = [...weak, ...unknown]
  if (s.status === 'insufficient_evidence') return `Not enough evidence yet${gaps.length ? `: ${list(gaps)}` : ''}.`
  if (strong.length === SCORE_PARTS.length) return `Strong on every measure: ${list(strong)}.`
  const parts = [...(strong.length ? [cap(list(strong))] : []), ...(gaps.length ? [strong.length ? `but ${list(gaps)}` : cap(list(gaps))] : [])]
  return parts.length ? `${parts.join(', ')}.` : 'Middling on every measure.'
}

/** Why this account sits below the one above it: the measure where it falls furthest short. Null when either is rejected. */
export function rankNote(prev: Pick<Account, 'name' | 'score'> | undefined, cur: Pick<Account, 'score'>): string | null {
  if (!prev || prev.score.rejections.length || cur.score.rejections.length) return null
  let worst: { k: string; d: number } | null = null
  for (const k of SCORE_PARTS) {
    const a = prev.score.components[k], b = cur.score.components[k]
    if (!a?.known || !b?.known || a.value === null || b.value === null) continue
    const d = a.value - b.value
    if (d > 0 && (!worst || d > worst.d)) worst = { k, d }
  }
  const above = prev.name ?? 'the account above'
  if (!worst) return `Level with ${above}.`
  return `${worst.d >= 25 ? 'Well behind' : worst.d >= 8 ? 'Behind' : 'Slightly behind'} ${above} on ${SCORE_LABEL[worst.k].toLowerCase()}.`
}

/** The tools Trigger Point reaches through Claude Code. Gmail and Calendar are needed to reach people and book
 *  meetings; Wispr Flow only saves typing transcripts, so it is optional. All three connect on one claude.ai page. */
export type ConnState = 'connected' | 'needs_sign_in' | 'failed' | 'not_connected'
export const CONNECTORS = [
  { id: 'claude.ai Gmail', name: 'Gmail', why: 'Sends your approved emails and reads the replies.', required: true },
  { id: 'claude.ai Google Calendar', name: 'Google Calendar', why: 'Finds the times you are free and books the meetings.', required: true },
  { id: 'claude.ai Wispr Flow', name: 'Wispr Flow', why: 'Reads your meeting transcripts so Trigger Point can learn from them.', required: false },
]

export function connState(harness: Pick<Harness, 'id' | 'state'>[], id: string): ConnState {
  const s = harness.find(h => h.id === id)?.state
  return s === 'connected' ? 'connected' : s === 'needs_auth' ? 'needs_sign_in' : s === 'failed' ? 'failed' : 'not_connected'
}

export function connectionRows(harness: Pick<Harness, 'id' | 'state'>[], optionalSkipped: boolean) {
  return CONNECTORS.map(c => {
    const state = connState(harness, c.id)
    return { ...c, state, skipped: !c.required && optionalSkipped && state !== 'connected' }
  })
}

/** Nothing left to ask: every required tool is connected and each optional one is connected or skipped. */
export const connectionsReady = (rows: ReturnType<typeof connectionRows>) => rows.every(r => r.state === 'connected' || r.skipped)

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

/** Contact buttons exist only for values that pass these checks, so nothing odd ever becomes a link. */
export const isEmail = (v: string) => /^[^\s@<>"',;]+@[^\s@<>"',;]+\.[^\s@<>"',;]+$/.test(v)
export const isPhone = (v: string) => /^\+?[0-9][0-9 ()\-.]{5,19}$/.test(v)
/** A blank Gmail compose window addressed to them. The person writes and sends it; nothing is sent from here. */
export const gmailCompose = (email: string) => (isEmail(email) ? `https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(email)}` : undefined)
export const telHref = (phone: string) => (isPhone(phone) ? `tel:${phone.replace(/[^\d+]/g, '')}` : undefined)

/** The professional-network link, labelled LinkedIn when the host says so and a plain Profile otherwise. */
export function profileLink(url?: string | null): { href: string; label: 'LinkedIn' | 'Profile' } | undefined {
  const href = safeHref(url)
  if (!href) return undefined
  try { return { href, label: new URL(href).hostname.toLowerCase().includes('linkedin') ? 'LinkedIn' : 'Profile' } } catch { return undefined }
}

/** The provider's deliverability word, shown as given apart from the two cases that are unambiguous. */
export function contactStatus(status?: string | null): { text: string; tone: string } | undefined {
  const t = status?.trim().toLowerCase()
  if (!t) return undefined
  if (['valid', 'verified', 'deliverable'].includes(t)) return { text: 'Verified', tone: 'good' }
  if (['invalid', 'undeliverable', 'bounced'].includes(t)) return { text: 'Invalid', tone: 'bad' }
  return { text: t.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase()), tone: 'warn' }
}

export function initials(name?: string | null): string {
  const parts = (name ?? '').trim().split(/\s+/).filter(Boolean)
  return parts.length ? (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase() : '?'
}

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
